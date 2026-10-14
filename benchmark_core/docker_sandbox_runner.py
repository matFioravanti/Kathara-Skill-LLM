"""Esegue Codex tramite Docker Sandboxes (sbx) con sandbox monouso per ogni run.

Architettura:
- Ogni run crea un sandbox Codex con nome univoco tramite `sbx create`, --skills=off,
  accesso esclusivo alla copia temporanea del laboratorio.
- I file del laboratorio sono montati direttamente nel sandbox: le modifiche
  vengono scritte istantaneamente sull'host senza necessita' di `sbx cp`.
- La memoria interna di Codex viene esplicitamente disabilitata (`--disable memories`,
  `-c memories=false`, `-c memories.use_memories=false`, `-c memories.generate_memories=false`,
  `-c features.memories=false`).
- Al termine (successo, errore, timeout, interruzione) il sandbox viene
  eliminato con `sbx rm --force` (con retry). Se il cleanup fallisce, la run
  fallisce con `SandboxCleanupError`.
- Il Kathara Lab Checker rimane sull'host: non e' mai montato nel sandbox.
- Nessun fallback silenzioso verso l'esecuzione host.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .workspace import write_json


# ---------------------------------------------------------------------------
# Versioni attese
# ---------------------------------------------------------------------------

EXPECTED_SBX_VERSION = "0.48.0"
DEFAULT_CODEX_SANDBOX_VERSION = "0.149.1"


# ---------------------------------------------------------------------------
# Eccezioni
# ---------------------------------------------------------------------------

class SandboxError(RuntimeError):
    """Errore tecnico del sandbox: nessun fallback verso l'esecuzione host."""


class SandboxDaemonError(SandboxError):
    """Il daemon sbx non e' disponibile e non e' stato possibile avviarlo."""


class SandboxAuthError(SandboxError):
    """L'utente non e' autenticato con Docker / sbx."""


class SandboxCleanupError(SandboxError):
    """Il sandbox non e' stato eliminato correttamente (blocca la run come fallita)."""


# ---------------------------------------------------------------------------
# Risultato della run sandbox
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxRun:
    sandbox_name: str
    sandbox_id: str | None          # ID effettivo dopo la creazione
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    codex_duration_seconds: float   # Solo Codex; non include overhead sbx
    sandbox_overhead_seconds: float # Creazione + eliminazione
    timed_out: bool
    cleanup_ok: bool
    cleanup_error: str | None
    final_message: str | None
    usage: dict[str, Any] | None
    sbx_version: str | None

    @property
    def success(self) -> bool:
        return not self.timed_out and self.returncode == 0 and self.cleanup_ok


# ---------------------------------------------------------------------------
# Utility sbx
# ---------------------------------------------------------------------------

def sbx_executable() -> str:
    exe = shutil.which("sbx")
    if not exe:
        raise SandboxError("sbx non trovato nel PATH. Installa Docker Sandboxes v0.48.0.")
    return exe


def sbx_version() -> str:
    """Legge la versione di sbx (formato: 'sbx version v0.48.0 <hash>')."""
    exe = sbx_executable()
    result = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise SandboxError(f"sbx version fallito: {result.stderr.strip()}")
    output = result.stdout.strip()
    for token in output.split():
        if token.startswith("v") and token[1:2].isdigit():
            return token[1:]    # strip leading 'v'
        if token and token[0].isdigit() and "." in token:
            return token
    raise SandboxError(f"Impossibile estrarre la versione da: {output!r}")


def sbx_daemon_status() -> bool:
    """Restituisce True se il daemon e' running."""
    exe = sbx_executable()
    result = subprocess.run([exe, "daemon", "status"], capture_output=True, text=True, timeout=15)
    combined = (result.stdout + result.stderr).lower()
    # "Status:  running" oppure "Status:  stopped"
    if "running" in combined:
        # Evita falso positivo se "stopped" precede "running" nel testo
        idx_running = combined.find("running")
        idx_stopped = combined.find("stopped")
        return idx_stopped < 0 or idx_running < idx_stopped
    return False


def sbx_daemon_ensure_running(*, auto_start: bool = True, wait_seconds: int = 30) -> None:
    """Verifica che il daemon sia attivo; se spento e auto_start=True lo avvia.

    Non interagisce con l'utente. Se non e' possibile avviarlo lancia SandboxDaemonError.
    """
    if sbx_daemon_status():
        return
    if not auto_start:
        raise SandboxDaemonError(
            "Il daemon sbx non e' in esecuzione. Avvialo manualmente con: sbx daemon start --detach"
        )
    exe = sbx_executable()
    start_result = subprocess.run(
        [exe, "daemon", "start", "--detach"],
        capture_output=True, text=True, timeout=30
    )
    if start_result.returncode:
        stderr = start_result.stderr.strip()
        if "already" in stderr.lower() or "running" in stderr.lower():
            return
        raise SandboxDaemonError(
            f"Impossibile avviare il daemon sbx automaticamente:\n{stderr}\n"
            "Avvialo manualmente con: sbx daemon start --detach"
        )
    # Attendi che il daemon sia operativo
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(1)
        if sbx_daemon_status():
            return
    raise SandboxDaemonError(
        f"Il daemon sbx non e' diventato operativo entro {wait_seconds}s dopo l'avvio automatico."
    )


def sbx_check_auth() -> None:
    """Verifica che l'utente sia autenticato con Docker / sbx.

    Usa `sbx ls` come proxy: se l'output contiene parole chiave di autenticazione
    lancia SandboxAuthError.
    """
    exe = sbx_executable()
    result = subprocess.run([exe, "ls"], capture_output=True, text=True, timeout=30)
    combined = (result.stdout + result.stderr).lower()
    auth_keywords = ("login", "authenticate", "not logged", "unauthorized", "sign in")
    if any(kw in combined for kw in auth_keywords):
        raise SandboxAuthError(
            "sbx / Docker non autenticato. Esegui `sbx login` o `docker login` e riprova."
        )


def sbx_check_docker_engine(*, auto_start: bool = True, wait_seconds: int = 45) -> None:
    """Verifica che Docker Engine sia raggiungibile. Se spento e auto_start=True tenta l'avvio su macOS."""
    docker = shutil.which("docker")
    if not docker:
        raise SandboxError("Docker CLI non trovata nel PATH.")
    result = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=15)
    if result.returncode == 0:
        return

    if not auto_start or sys.platform != "darwin":
        raise SandboxError(
            f"Docker Engine non raggiungibile (`docker info` fallito):\n{result.stderr.strip()}\n"
            "Avvia Docker Desktop e riprova."
        )

    # Tenta l'avvio automatico di Docker Desktop su macOS
    try:
        subprocess.run(["open", "-a", "Docker"], capture_output=True, text=True, timeout=15)
    except Exception as exc:
        raise SandboxError(f"Impossibile avviare Docker Desktop tramite 'open -a Docker': {exc}")

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(2)
        probe = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=10)
        if probe.returncode == 0:
            return

    raise SandboxError(
        f"Docker Engine non e' diventato raggiungibile entro {wait_seconds}s dopo l'avvio automatico di Docker Desktop."
    )


def sbx_check_sandbox_codex(*, expected_version: str | None = None) -> str:
    """Verifica versione e autenticazione di Codex all'interno di un sandbox reale.

    Crea un probe temporaneo con `sbx create codex`, monta auth.json (se presente),
    esegue `codex --version` e `codex login status`, quindi elimina il sandbox.
    Non consuma token LLM.
    """
    exe = sbx_executable()
    probe_name = f"sbx-preflight-{uuid.uuid4().hex[:8]}"
    host_auth = Path.home() / ".codex" / "auth.json"

    with tempfile.TemporaryDirectory(prefix="sbx-preflight-ws-") as tmpdir:
        create_cmd = [exe, "create", "codex", tmpdir]
        if host_auth.is_file():
            create_cmd.append(f"{host_auth.resolve()}:ro")
        create_cmd.extend(["--name", probe_name, "--skills", "off"])

        create_res = subprocess.run(create_cmd, capture_output=True, text=True, timeout=60)
        if create_res.returncode != 0:
            raise SandboxError(
                f"Impossibile creare probe sandbox per verifica Codex:\n{create_res.stderr.strip() or create_res.stdout.strip()}"
            )

        try:
            if host_auth.is_file():
                subprocess.run(
                    [exe, "exec", probe_name, "ln", "-sf", str(host_auth.resolve()), "/home/agent/.codex/auth.json"],
                    capture_output=True, text=True, timeout=15, check=False,
                )

            # 1. Verifica versione Codex nel sandbox
            ver_res = subprocess.run([exe, "exec", probe_name, "codex", "--version"], capture_output=True, text=True, timeout=30)
            if ver_res.returncode != 0:
                raise SandboxError(f"Verifica versione Codex nel sandbox fallita: {ver_res.stderr.strip()}")

            match = re.search(r"(?:v)?(\d+\.\d+\.\d+(?:-\w+)?)", ver_res.stdout)
            if not match:
                raise SandboxError(f"Impossibile estrarre versione valida da output Codex sandbox: {ver_res.stdout!r}")
            actual_ver = match.group(1)

            if expected_version and actual_ver != expected_version:
                raise SandboxError(
                    f"Codex Sandbox version mismatch:\n"
                    f"  attesa:   {expected_version}\n"
                    f"  rilevata: {actual_ver}"
                )

            # 2. Verifica login status nel sandbox
            login_res = subprocess.run([exe, "exec", probe_name, "codex", "login", "status"], capture_output=True, text=True, timeout=30)
            if login_res.returncode != 0:
                raise SandboxAuthError(
                    "Codex non risulta autenticato all'interno del sandbox (`codex login status` fallito).\n"
                    "Verifica che `~/.codex/auth.json` sia presente e valido sull'host oppure configura `sbx secret set openai`."
                )
            return actual_ver
        finally:
            _sbx_rm(probe_name)


# ---------------------------------------------------------------------------
# Gestione ciclo di vita sandbox
# ---------------------------------------------------------------------------

def _unique_sandbox_name(scenario_id: str, run_number: int) -> str:
    """Nome univoco per il sandbox: kathara-<scenario>-r<NNN>-<uuid4[:8]>."""
    suffix = uuid.uuid4().hex[:8]
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in scenario_id.lower())
    safe = safe[:20].strip("-")
    return f"kathara-{safe}-r{run_number:03d}-{suffix}"


def _sbx_rm(sandbox_name: str, *, timeout: int = 30) -> tuple[bool, str | None]:
    """Elimina il sandbox con fino a 2 tentativi in caso di fallimento. Restituisce (ok, error_message)."""
    exe = sbx_executable()
    last_err: str | None = None
    for attempt in range(2):
        try:
            result = subprocess.run(
                [exe, "rm", "--force", sandbox_name],
                capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                return True, None
            last_err = result.stderr.strip() or result.stdout.strip()
        except subprocess.TimeoutExpired:
            last_err = f"sbx rm --force {sandbox_name} scaduto dopo {timeout}s"
        except Exception as exc:  # pragma: no cover
            last_err = str(exc)
        if attempt == 0:
            time.sleep(1)
    return False, last_err


# ---------------------------------------------------------------------------
# Parsing eventi JSONL Codex (rispecchia codex_cli_runner.parse_events)
# ---------------------------------------------------------------------------

def _parse_events(stdout: str) -> tuple[str | None, dict[str, Any] | None]:
    final_message = None
    usage = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            final_message = item["text"]
        if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return final_message, usage


# ---------------------------------------------------------------------------
# Esecuzione principale
# ---------------------------------------------------------------------------

def run_codex_in_sandbox(
    *,
    prompt: str,
    workspace: Path,
    logs: Path,
    timeout: int,
    model: str | None,
    reasoning_effort: str | None,
    variant: str,
    sandbox_name: str,
    auto_start_daemon: bool = True,
    daemon_wait_seconds: int = 30,
) -> SandboxRun:
    """Crea un sandbox Codex monouso, esegue il prompt, raccoglie i risultati ed elimina il sandbox.

    - Usa `sbx create codex <workspace>` per creare il sandbox senza sessione interattiva.
    - Il workspace host e' montato direttamente (bind mount): le modifiche sono subito su disco host.
    - La memoria interna di Codex e' esplicitamente disabilitata per isolamento totale.
    - Il Kathara Lab Checker NON viene montato nel sandbox.
    - Cleanup garantito tramite try/finally. Un cleanup fallito genera SandboxCleanupError.
    """
    if not workspace.is_dir():
        raise SandboxError(f"Workspace non trovato: {workspace}")
    logs.mkdir(parents=True, exist_ok=True)

    exe = sbx_executable()
    detected_version: str | None = None
    try:
        detected_version = sbx_version()
    except SandboxError:
        pass

    overhead_times: list[float] = []
    sandbox_id: str | None = None
    host_auth = Path.home() / ".codex" / "auth.json"

    # ------------------------------------------------------------------
    # 1. Crea sandbox Codex con nome univoco e --skills=off
    #    sbx create codex <workspace> [auth.json:ro] --name <name> --skills off
    # ------------------------------------------------------------------
    create_start = time.monotonic()
    create_cmd = [
        exe, "create", "codex",
        str(workspace.resolve()),
    ]
    if host_auth.is_file():
        create_cmd.append(f"{host_auth.resolve()}:ro")
    create_cmd.extend([
        "--name", sandbox_name,
        "--skills", "off",
    ])
    create_result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=120)
    overhead_times.append(time.monotonic() - create_start)

    if create_result.returncode:
        stderr = create_result.stderr.strip() or create_result.stdout.strip()
        raise SandboxError(
            f"Impossibile creare il sandbox {sandbox_name!r}:\n{stderr}"
        )
    # L'ID/nome e' presente nell'output di creazione
    lines = [ln.strip() for ln in create_result.stdout.strip().splitlines() if ln.strip()]
    sandbox_id = lines[-1] if lines else None

    # Se auth.json e' montato, linka in /home/agent/.codex/auth.json
    if host_auth.is_file():
        subprocess.run(
            [exe, "exec", sandbox_name, "ln", "-sf", str(host_auth.resolve()), "/home/agent/.codex/auth.json"],
            capture_output=True, text=True, timeout=15, check=False,
        )

    # ------------------------------------------------------------------
    # Cleanup garantito tramite try/finally
    # ------------------------------------------------------------------
    rm_ok = True
    rm_err: str | None = None
    codex_duration = 0.0
    codex_returncode = -1
    codex_stdout = ""
    codex_stderr = ""
    timed_out = False
    final_message: str | None = None
    usage: dict[str, Any] | None = None
    full_command: tuple[str, ...] = ()

    try:
        # --------------------------------------------------------------
        # 2. Esegui Codex non-interattivamente nel sandbox via sbx exec
        #    sbx exec -w <workspace> -i <name> codex exec --json --ephemeral ... -C <workspace> -
        # --------------------------------------------------------------
        codex_args: list[str] = [
            "codex", "exec",
            "--json",
            "--ephemeral",
            "--disable", "memories",
            "-c", "memories=false",
            "-c", "memories.use_memories=false",
            "-c", "memories.generate_memories=false",
            "-c", "features.memories=false",
            "--sandbox", "workspace-write",
            "--skip-git-repo-check",
            "-C", str(workspace.resolve()),
        ]
        if model:
            codex_args += ["--model", model]
        if reasoning_effort:
            codex_args += ["-c", f'model_reasoning_effort="{reasoning_effort}"']
        codex_args.append("-")

        full_command = tuple([exe, "exec", "-w", str(workspace.resolve()), "-i", sandbox_name] + codex_args)

        # Impedisce selezione via API key; preserva login locale ChatGPT
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)

        codex_start = time.monotonic()
        try:
            completed = subprocess.run(
                list(full_command),
                input=prompt,
                text=True,
                capture_output=True,
                env=env,
                timeout=timeout,
                check=False,
            )
            codex_stdout = completed.stdout or ""
            codex_stderr = completed.stderr or ""
            codex_returncode = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            codex_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            codex_stderr = (exc.stderr if isinstance(exc.stderr, str) else "")
            codex_stderr += f"\nCodex in sandbox timed out after {timeout}s.\n"
            codex_returncode = 124
            timed_out = True
        codex_duration = time.monotonic() - codex_start

        final_message, usage = _parse_events(codex_stdout)

    finally:
        # --------------------------------------------------------------
        # 3. Elimina sandbox (sempre: successo, errore, timeout, Ctrl-C)
        # --------------------------------------------------------------
        rm_start = time.monotonic()
        rm_ok, rm_err = _sbx_rm(sandbox_name)
        overhead_times.append(time.monotonic() - rm_start)

    # ------------------------------------------------------------------
    # 4. Persisti artefatti di log
    # ------------------------------------------------------------------
    (logs / "events.jsonl").write_text(codex_stdout, encoding="utf-8")
    (logs / "stderr.log").write_text(codex_stderr, encoding="utf-8")
    (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")

    sandbox_overhead = sum(overhead_times)

    write_json(logs / "invocation.json", {
        "command": list(full_command),
        "cwd": str(workspace.resolve()),
        "variant": variant,
        "execution_backend": "docker_sandbox",
        "authentication": "local_chatgpt_login",
        "api_key_used": False,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox_name": sandbox_name,
        "sandbox_id": sandbox_id,
        "sbx_version": detected_version,
    })
    write_json(logs / "result.json", {
        "returncode": codex_returncode,
        "timed_out": timed_out,
        "duration_seconds": codex_duration,
        "sandbox_overhead_seconds": sandbox_overhead,
        "final_message": final_message,
        "usage": usage,
    })
    write_json(logs / "sandbox_metadata.json", {
        "sandbox_name": sandbox_name,
        "sandbox_id": sandbox_id,
        "sbx_version": detected_version,
        "execution_backend": "docker_sandbox",
        "cleanup_ok": rm_ok,
        "cleanup_error": rm_err,
        "overhead_seconds": sandbox_overhead,
        "codex_duration_seconds": codex_duration,
    })

    result = SandboxRun(
        sandbox_name=sandbox_name,
        sandbox_id=sandbox_id,
        command=full_command,
        returncode=codex_returncode,
        stdout=codex_stdout,
        stderr=codex_stderr,
        codex_duration_seconds=codex_duration,
        sandbox_overhead_seconds=sandbox_overhead,
        timed_out=timed_out,
        cleanup_ok=rm_ok,
        cleanup_error=rm_err,
        final_message=final_message,
        usage=usage,
        sbx_version=detected_version,
    )

    if codex_returncode != 0 or timed_out:
        detail = codex_stderr.strip() or "nessun dettaglio in stderr"
        if not rm_ok:
            detail += f" (Inoltre cleanup sandbox fallito: {rm_err})"
        raise SandboxError(
            f"Codex in Docker Sandbox fallito (exit {codex_returncode}): {detail}"
        )
    if not rm_ok:
        raise SandboxCleanupError(
            f"Cleanup del sandbox {sandbox_name} fallito: {rm_err}"
        )
    return result


# ---------------------------------------------------------------------------
# Preflight Docker Sandbox
# ---------------------------------------------------------------------------

def preflight_docker_sandbox(
    *,
    auto_start_daemon: bool = True,
    auto_start_docker: bool = True,
    daemon_wait_seconds: int = 30,
    docker_wait_seconds: int = 45,
    expected_sbx_version: str = EXPECTED_SBX_VERSION,
) -> str:
    """Verifica e prepara l'ambiente Docker Sandbox.

    Controlla:
    1. sbx nel PATH
    2. Versione sbx == expected_sbx_version
    3. Docker Engine raggiungibile (tenta avvio Docker Desktop se auto_start_docker)
    4. Daemon sbx in esecuzione (avvia automaticamente se auto_start_daemon)
    5. Autenticazione Docker / sbx

    Restituisce la versione sbx rilevata.
    Lancia SandboxError (o sottoclasse) in caso di errore senza fallback host.
    """
    sbx_executable()          # 1. sbx nel PATH

    detected = sbx_version()  # 2. versione
    if detected != expected_sbx_version:
        raise SandboxError(
            f"Versione sbx non corrispondente:\n"
            f"  attesa:   {expected_sbx_version}\n"
            f"  rilevata: {detected}\n"
            "Aggiorna o specifica la versione corretta in docker_sandbox.sbx_version."
        )

    sbx_check_docker_engine(  # 3. Docker Engine
        auto_start=auto_start_docker,
        wait_seconds=docker_wait_seconds,
    )

    sbx_daemon_ensure_running(  # 4. Daemon
        auto_start=auto_start_daemon,
        wait_seconds=daemon_wait_seconds,
    )

    sbx_check_auth()  # 5. Autenticazione

    return detected
