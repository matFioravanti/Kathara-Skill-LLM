"""Esegue Codex tramite Docker Sandboxes (sbx) con sandbox monouso per ogni run.

Architettura:
- Ogni run crea un sandbox Codex con nome univoco tramite `sbx create`, --skills=off,
  accesso esclusivo alla copia temporanea del laboratorio.
- I file del laboratorio sono montati direttamente nel sandbox: le modifiche
  vengono scritte istantaneamente sull'host senza necessita' di `sbx cp`.
- Autenticazione: usa esclusivamente l'infrastruttura ufficiale di Docker Sandboxes
  (OAuth token / secret gestito dal proxy sbx, nessun mount di credenziali file host).
- La memoria interna di Codex viene esplicitamente disabilitata (`--disable memories`,
  `-c memories=false`, `-c memories.use_memories=false`, `-c memories.generate_memories=false`,
  `-c features.memories=false`).
- Al termine (successo, errore, timeout, interruzione, o fallimento parziale) il sandbox viene
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
    """L'utente non e' autenticato con Docker / sbx o OpenAI OAuth."""


class SandboxPolicyError(SandboxError):
    """La network policy del sandbox e' errata (endpoint negato o non autorizzato consentito)."""


class SandboxProbeError(SandboxError):
    """Fallimento durante le verifiche probe interne del sandbox (versione, memoria)."""


class SandboxExecutionError(SandboxError):
    """Fallimento del processo Codex all'interno del sandbox."""


class SandboxCleanupError(SandboxError):
    """Il sandbox non e' stato eliminato correttamente (blocca la run come fallita)."""


class SandboxArtifactError(SandboxError):
    """Fallimento nella scrittura o persistenza degli artefatti essenziali del sandbox."""


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
    codex_version: str | None = None
    codex_host_version: str | None = None
    codex_sandbox_version: str | None = None
    artifacts_ok: bool = True
    artifact_errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return (
            not self.timed_out
            and self.returncode == 0
            and self.cleanup_ok
            and self.artifacts_ok
        )


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
        idx_running = combined.find("running")
        idx_stopped = combined.find("stopped")
        return idx_stopped < 0 or idx_running < idx_stopped
    return False


def sbx_daemon_ensure_running(*, auto_start: bool = True, wait_seconds: int = 30) -> None:
    """Verifica che il daemon sia attivo; se spento e auto_start=True lo avvia."""
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
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(1)
        if sbx_daemon_status():
            return
    raise SandboxDaemonError(
        f"Il daemon sbx non e' diventato operativo entro {wait_seconds}s dopo l'avvio automatico."
    )


def sbx_check_auth() -> None:
    """Verifica che l'utente sia autenticato con Docker e Docker Sandboxes OAuth/Secret.

    Verifica sia l'accesso CLI sbx/Docker sia la presenza di credenziali OAuth/secret
    per il servizio 'openai' senza esporre credenziali all'interno del filesystem del sandbox.
    """
    exe = sbx_executable()
    result = subprocess.run([exe, "ls"], capture_output=True, text=True, timeout=30)
    combined = (result.stdout + result.stderr).lower()
    auth_keywords = ("authenticate", "not logged", "unauthorized", "sign in")
    if any(kw in combined for kw in auth_keywords):
        raise SandboxAuthError(
            "sbx / Docker non autenticato. Esegui `sbx login` o `docker login` e riprova."
        )

    # Verifica la presenza di credenziali/OAuth gestite da Docker Sandboxes
    sec_res = subprocess.run([exe, "secret", "ls", "--json"], capture_output=True, text=True, timeout=15)
    if sec_res.returncode == 0:
        try:
            data = json.loads(sec_res.stdout)
            if isinstance(data, dict):
                secrets = data.get("secrets", [])
            elif isinstance(data, list):
                secrets = data
            else:
                secrets = []
            has_openai = any(
                isinstance(s, dict) and (s.get("service") == "openai" or s.get("name") == "openai")
                for s in secrets
            )
            # Se è presente nei secret salvati, la verifica ha successo
            if has_openai:
                return
        except json.JSONDecodeError:
            pass

    # Se non presente in secret ls, controlla se sbx rileva login OAuth o secret attivo
    # Se nè secret ls nè OAuth configurati, avvisa l'utente
    sec_plain = subprocess.run([exe, "secret", "ls"], capture_output=True, text=True, timeout=15)
    if "openai" in (sec_plain.stdout + sec_plain.stderr).lower():
        return

    # In assenza di secret sbx memorizzato, segnala chiaramente la procedura iniziale necessaria
    raise SandboxAuthError(
        "Nessuna autenticazione OAuth o secret per OpenAI configurata in Docker Sandboxes.\n"
        "Procedura iniziale necessaria:\n"
        "  1. Per autenticazione OAuth ufficiale gestita da Docker Sandboxes (consigliato, senza esporre credenziali):\n"
        "     sbx secret set openai --oauth\n"
        "  2. Oppure tramite token/chiave protetta memorizzata nel secret store di Docker Sandboxes:\n"
        "     sbx secret set openai\n"
        "Nessun file ~/.codex/auth.json viene montato o esposto nel sandbox."
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


def sbx_check_network_policy(sandbox_name: str) -> None:
    """Verifica che la policy di rete del sandbox consenta la comunicazione con il modello e blocchi il resto.

    Interpreta il risultato analizzando il campo 'allowed' del JSON restituito da
    `sbx policy check network [--sandbox SANDBOX] TARGET --json` (v0.48.0), senza
    affidarsi al solo exit code.
    Non altera la policy globale del sistema.
    """
    exe = sbx_executable()

    # Endpoint necessari per la comunicazione del modello con OpenAI
    required_endpoints = [
        "api.openai.com:443",
        "chatgpt.com:443",
    ]
    for target in required_endpoints:
        res = subprocess.run(
            [exe, "policy", "check", "network", "--sandbox", sandbox_name, "--json", target],
            capture_output=True, text=True, timeout=15,
        )
        try:
            data = json.loads(res.stdout)
            is_allowed = data.get("allowed") is True
        except (json.JSONDecodeError, AttributeError):
            is_allowed = (res.returncode == 0)

        if not is_allowed:
            detail = res.stderr.strip() or res.stdout.strip()
            raise SandboxPolicyError(
                f"Policy di rete errata per {sandbox_name}: connessione necessaria a {target} negata.\n{detail}"
            )

    # Endpoint non autorizzati che devono essere rigorosamente bloccati
    blocked_endpoints = [
        "unauthorized-domain.com:443",
        "google.com:443",
    ]
    for target in blocked_endpoints:
        res = subprocess.run(
            [exe, "policy", "check", "network", "--sandbox", sandbox_name, "--json", target],
            capture_output=True, text=True, timeout=15,
        )
        try:
            data = json.loads(res.stdout)
            is_allowed = data.get("allowed") is True
        except (json.JSONDecodeError, AttributeError):
            is_allowed = (res.returncode == 0)

        if is_allowed:
            raise SandboxPolicyError(
                f"Policy di rete errata per {sandbox_name}: connessione verso destinazione non autorizzata {target} consentita."
            )


def sbx_get_sandbox_id(sandbox_name: str) -> str | None:
    """Recupera l'ID reale (UUID) del sandbox tramite comandi sbx (es. `sbx ls --json`).

    Se non disponibile, non trovato o se il valore e' un messaggio testuale,
    restituisce None (salvato come null in JSON). Non usa mai stringhe del tipo '✓ Created sandbox ...'.
    """
    try:
        exe = sbx_executable()
        res = subprocess.run([exe, "ls", "--json"], capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            items = json.loads(res.stdout)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("name") == sandbox_name:
                        cand_id = item.get("id")
                        if isinstance(cand_id, str):
                            cand_id = cand_id.strip()
                            if cand_id and not cand_id.startswith("✓") and "created" not in cand_id.lower():
                                return cand_id
    except Exception:
        pass
    return None


def sbx_host_codex_version() -> str | None:
    """Rileva la versione di Codex installata sull'host, se disponibile."""
    codex_exe = shutil.which("codex")
    if not codex_exe or not Path(codex_exe).name.startswith("codex"):
        return None
    try:
        res = subprocess.run([codex_exe, "--version"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            match = re.search(r"(?:v)?(\d+\.\d+\.\d+(?:-\w+)?)", res.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def sbx_check_sandbox_codex(*, expected_version: str | None = None) -> str:
    """Verifica versione, memoria e autenticazione di Codex all'interno di un sandbox reale.

    Crea un probe monouso con `sbx create codex`, garantendo il cleanup immediato anche
    in caso di fallimento della creazione parziale o dell'esecuzione.
    Verifica che il binario Codex supporti realmente il disabilitamento della memoria
    interrogando direttamente lo stato della feature nel runtime.
    Non espone alcun file auth.json nel sandbox.
    Non consuma token LLM.
    """
    exe = sbx_executable()
    probe_name = f"sbx-preflight-{uuid.uuid4().hex[:8]}"

    with tempfile.TemporaryDirectory(prefix="sbx-preflight-ws-") as tmpdir:
        create_cmd = [exe, "create", "codex", tmpdir, "--name", probe_name, "--skills", "off"]

        try:
            create_res = subprocess.run(create_cmd, capture_output=True, text=True, timeout=60)
            if create_res.returncode != 0:
                raise SandboxProbeError(
                    f"Impossibile creare probe sandbox per verifica Codex:\n{create_res.stderr.strip() or create_res.stdout.strip()}"
                )

            # 1. Verifica versione Codex nel sandbox
            ver_res = subprocess.run([exe, "exec", probe_name, "codex", "--version"], capture_output=True, text=True, timeout=30)
            if ver_res.returncode != 0:
                raise SandboxProbeError(f"Verifica versione Codex nel sandbox fallita: {ver_res.stderr.strip()}")

            match = re.search(r"(?:v)?(\d+\.\d+\.\d+(?:-\w+)?)", ver_res.stdout)
            if not match:
                raise SandboxProbeError(f"Impossibile estrarre versione valida da output Codex sandbox: {ver_res.stdout!r}")
            actual_ver = match.group(1)

            if expected_version and actual_ver != expected_version:
                raise SandboxProbeError(
                    f"Codex Sandbox version mismatch:\n"
                    f"  attesa:   {expected_version}\n"
                    f"  rilevata: {actual_ver}"
                )

            # 2. Verifica reale supporto flag di disabilitazione memoria nel binario interno
            # Esegue `codex --disable memories features list` verificando che features elenchi
            # 'memories' e che sia disabilitato ('false').
            mem_test_cmd = [
                exe, "exec", probe_name, "codex",
                "--disable", "memories",
                "-c", "memories=false",
                "-c", "memories.use_memories=false",
                "-c", "memories.generate_memories=false",
                "-c", "features.memories=false",
                "features", "list",
            ]
            mem_test_res = subprocess.run(mem_test_cmd, capture_output=True, text=True, timeout=30)
            if mem_test_res.returncode != 0:
                raise SandboxProbeError(
                    f"I flag di disabilitazione memoria non sono supportati dalla versione Codex nel sandbox:\n"
                    f"{mem_test_res.stderr.strip() or mem_test_res.stdout.strip()}"
                )
            mem_lines = [ln for ln in mem_test_res.stdout.splitlines() if ln.startswith("memories")]
            if not mem_lines or "false" not in mem_lines[0]:
                raise SandboxProbeError(
                    f"La feature memoria non risulta disabilitata nel sandbox:\n{mem_test_res.stdout}"
                )

            # 3. Verifica policy di rete del sandbox
            sbx_check_network_policy(probe_name)

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
    codex_host_version: str | None = None,
    auto_start_daemon: bool = True,
    daemon_wait_seconds: int = 30,
    sampling_mode: str = "passive",
) -> SandboxRun:
    """Crea un sandbox Codex monouso, esegue il prompt, raccoglie i risultati ed elimina il sandbox.

    - Usa `sbx create codex <workspace>` per creare il sandbox senza sessione interattiva.
    - Il workspace host e' montato direttamente (bind mount): le modifiche sono subito su disco host.
    - Usa l'autenticazione OAuth ufficiale di sbx (nessun file auth.json montato nel sandbox).
    - La memoria interna di Codex e' esplicitamente disabilitata per isolamento totale.
    - Verifica il corretto isolamento della policy di rete prima dell'esecuzione.
    - Cleanup garantito tramite try/finally anche in caso di creazione parziale.
    - Un cleanup fallito genera SandboxCleanupError.
    """
    if not workspace.is_dir():
        raise SandboxError(f"Workspace non trovato: {workspace}")
    logs.mkdir(parents=True, exist_ok=True)

    exe = sbx_executable()
    detected_sbx_version: str | None = None
    detected_codex_version: str | None = None
    detected_codex_host_version: str | None = codex_host_version or sbx_host_codex_version()
    try:
        detected_sbx_version = sbx_version()
    except SandboxError:
        pass

    overhead_times: list[float] = []
    sandbox_id: str | None = None

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
    infra_error: Exception | None = None
    network_policy = None

    # ------------------------------------------------------------------
    # Cleanup garantito tramite try/finally per l'intero ciclo di vita
    # anche in caso di errore durante create o verifiche
    # ------------------------------------------------------------------
    try:
        # 1. Crea sandbox Codex con nome univoco e --skills=off
        #    sbx create codex <workspace> --name <name> --skills off
        create_start = time.monotonic()
        create_cmd = [
            exe, "create", "codex",
            str(workspace.resolve()),
            "--name", sandbox_name,
            "--skills", "off",
        ]
        create_result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=120)
        overhead_times.append(time.monotonic() - create_start)

        if create_result.returncode:
            stderr = create_result.stderr.strip() or create_result.stdout.strip()
            raise SandboxError(
                f"Impossibile creare il sandbox {sandbox_name!r}:\n{stderr}"
            )
        # Recupera ID reale tramite sbx ls --json; se non disponibile, salva None/null (mai il messaggio di creazione)
        sandbox_id = sbx_get_sandbox_id(sandbox_name)

        # 2. Leggi versione Codex effettiva all'interno del sandbox
        ver_proc = subprocess.run([exe, "exec", sandbox_name, "codex", "--version"], capture_output=True, text=True, timeout=30)
        if ver_proc.returncode == 0:
            match = re.search(r"(?:v)?(\d+\.\d+\.\d+(?:-\w+)?)", ver_proc.stdout)
            if match:
                detected_codex_version = match.group(1)

        # 3. Verifica policy di rete
        sbx_check_network_policy(sandbox_name)
        network_policy = "restricted"  # Endpoint modello consentiti; due destinazioni esterne bloccate.

        # 4. Esegui Codex non-interattivamente nel sandbox via sbx exec
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
            codex_stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            codex_stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            codex_stderr += f"\nCodex in sandbox timed out after {timeout}s.\n"
            codex_returncode = 124
            timed_out = True
        codex_duration = time.monotonic() - codex_start

        final_message, usage = _parse_events(codex_stdout)

    except Exception as exc:
        infra_error = exc
        if not codex_stderr:
            codex_stderr = str(exc)
        else:
            codex_stderr += f"\n{exc}\n"
        raise
    finally:
        # Cleanup garantito in qualunque caso
        rm_start = time.monotonic()
        rm_ok, rm_err = _sbx_rm(sandbox_name)
        overhead_times.append(time.monotonic() - rm_start)

        sandbox_overhead = sum(overhead_times)

        # Persisti SEMPRE gli artefatti di log e metadati senza nascondere silenziosamente errori
        log_errors: list[str] = []
        essential_errors: list[str] = []
        try:
            (logs / "events.jsonl").write_text(codex_stdout, encoding="utf-8")
        except Exception as exc:
            log_errors.append(f"events.jsonl: {exc}")
            essential_errors.append(f"events.jsonl: {exc}")
        try:
            (logs / "stderr.log").write_text(codex_stderr, encoding="utf-8")
        except Exception as exc:
            log_errors.append(f"stderr.log: {exc}")
        try:
            (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
        except Exception as exc:
            log_errors.append(f"prompt_sent.md: {exc}")

        from .sampling_telemetry import extract_sampling_telemetry, save_sampling_telemetry
        try:
            sampling_telemetry = extract_sampling_telemetry(logs, collection_mode=sampling_mode, backend="docker_sandbox")
            save_sampling_telemetry(logs, sampling_telemetry)
        except Exception as exc:
            log_errors.append(f"sampling_telemetry.json: {exc}")

        try:
            write_json(logs / "invocation.json", {
                "command": list(full_command),
                "cwd": str(workspace.resolve()),
                "variant": variant,
                "execution_backend": "docker_sandbox",
                "authentication": "sbx_oauth_proxy",
                "api_key_used": False,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "sampling_collection_mode": sampling_mode,
                "sampling_transport": None,
                "sandbox_name": sandbox_name,
                "sandbox_id": sandbox_id,
                "sbx_version": detected_sbx_version,
                "codex_host_version": detected_codex_host_version,
                "codex_sandbox_version": detected_codex_version,
            })
        except Exception as exc:
            log_errors.append(f"invocation.json: {exc}")
            essential_errors.append(f"invocation.json: {exc}")

        recorded_error = (
            str(infra_error)
            if infra_error
            else (
                f"CleanupError: {rm_err}"
                if not rm_ok
                else (
                    f"ArtifactPersistenceError: {'; '.join(essential_errors)}"
                    if essential_errors
                    else None
                )
            )
        )

        try:
            write_json(logs / "result.json", {
                "returncode": codex_returncode,
                "timed_out": timed_out,
                "duration_seconds": codex_duration,
                "sandbox_overhead_seconds": sandbox_overhead,
                "final_message": final_message,
                "usage": usage,
                "error": recorded_error,
            })
        except Exception as exc:
            log_errors.append(f"result.json: {exc}")
            essential_errors.append(f"result.json: {exc}")

        if not recorded_error and essential_errors:
            recorded_error = f"ArtifactPersistenceError: {'; '.join(essential_errors)}"

        try:
            write_json(logs / "sandbox_metadata.json", {
                "sandbox_name": sandbox_name,
                "sandbox_id": sandbox_id,
                "sbx_version": detected_sbx_version,
                "codex_host_version": detected_codex_host_version,
                "codex_sandbox_version": detected_codex_version,
                "execution_backend": "docker_sandbox",
                "cleanup_ok": rm_ok,
                "cleanup_error": rm_err,
                "overhead_seconds": sandbox_overhead,
                "codex_duration_seconds": codex_duration,
                "error": recorded_error,
                "network_policy": network_policy,
                "artifacts_ok": len(essential_errors) == 0,
                "artifact_errors": essential_errors if essential_errors else None,
            })
        except Exception as exc:
            log_errors.append(f"sandbox_metadata.json: {exc}")
            essential_errors.append(f"sandbox_metadata.json: {exc}")

        if log_errors:
            print(f"Avviso scrittura log sandbox in {logs}: {'; '.join(log_errors)}", file=sys.stderr)

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
        sbx_version=detected_sbx_version,
        codex_version=detected_codex_version,
        codex_host_version=detected_codex_host_version,
        codex_sandbox_version=detected_codex_version,
        artifacts_ok=len(essential_errors) == 0,
        artifact_errors=tuple(essential_errors),
    )

    if codex_returncode != 0 or timed_out:
        detail = codex_stderr.strip() or "nessun dettaglio in stderr"
        if not rm_ok:
            detail += f" (Inoltre cleanup sandbox fallito: {rm_err})"
        if essential_errors:
            detail += f" (Inoltre persistenza artefatti fallita: {'; '.join(essential_errors)})"
        if infra_error:
            raise SandboxExecutionError(
                f"Codex in Docker Sandbox fallito (exit {codex_returncode}): {detail}"
            ) from infra_error
        raise SandboxExecutionError(
            f"Codex in Docker Sandbox fallito (exit {codex_returncode}): {detail}"
        )
    if not rm_ok:
        cleanup_detail = f"Cleanup del sandbox {sandbox_name} fallito: {rm_err}"
        if essential_errors:
            cleanup_detail += f" (Inoltre persistenza artefatti fallita: {'; '.join(essential_errors)})"
        raise SandboxCleanupError(cleanup_detail)
    if essential_errors:
        raise SandboxArtifactError(
            f"Persistenza artefatti essenziali fallita in {logs}: {'; '.join(essential_errors)}"
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
    5. Autenticazione Docker / sbx OAuth

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


class ProtectedCodexSession:
    """Two sbx environments, one persisted Codex thread, no host execution fallback.

    Extends the existing sbx lifecycle/authentication helpers. No project, logs,
    checker, original lab or host credentials are mounted in the AUT.
    """

    def __init__(self, *, workspace, state, logs, config):
        self.workspace, self.state, self.logs = map(Path, (workspace, state, logs))
        self.config = config
        self.name = None
        self.thread_id = None
        self.uid = os.getuid() if os.getuid() else 65534
        self.gid = os.getgid() if os.getuid() else 65534
        self.cleanup = []
        self.commands = []
        self.turns = []
        self.readonly = True
        self.overhead = 0.0
        self.version = None

    def checked(self, args, timeout=90):
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env=self.environment())
        if result.returncode:
            # Do not print template config/auth content or environment.
            raise SandboxError(f'{args[:3]} failed: {result.stderr.strip()}')
        return result.stdout

    @staticmethod
    def environment():
        from .codex_cli_runner import codex_environment
        return codex_environment()

    def prefix(self):
        return [sbx_executable(), 'exec', '-i', '-u', 'root', '-w', str(self.workspace),
                '-e', 'HOME=/tmp/gate-user', '-e', 'CODEX_HOME='+str(self.state), self.name,
                'setpriv', '--reuid='+str(self.uid), '--regid='+str(self.gid),
                '--clear-groups', '--no-new-privs', '--bounding-set=-all',
                '--inh-caps=-all', '--ambient-caps=-all']

    def create(self, *, readonly):
        started = time.monotonic()
        if self.name:
            raise SandboxError('Cannot create a second live gate environment')
        self.readonly = readonly
        self.name = 'kathara-gate-' + uuid.uuid4().hex[:12]
        self.state.mkdir(parents=True, exist_ok=True)
        self.checked([sbx_executable(), 'create', 'codex', str(self.state),
                      str(self.workspace)+(':ro' if readonly else ''), '--name', self.name,
                      '--skills', 'off', '--pull', 'missing'], timeout=120)
        # Keep only the proxy provider configuration, never MCP, hooks, plugins,
        # inherited model instructions or exec policies. No secret is logged.
        setup = r'''
import pathlib,tomllib,json,os,sys
state=pathlib.Path(sys.argv[1]); uid,gid=map(int,sys.argv[2:])
home=pathlib.Path('/tmp/gate-user'); home.mkdir(exist_ok=True); os.chown(home,uid,gid)
source=tomllib.loads(pathlib.Path('/home/agent/.codex/config.toml').read_text())
provider=source.get('model_provider')
if not isinstance(provider,str) or provider not in source.get('model_providers',{}):
 raise RuntimeError('Missing sandbox proxy provider')
lines=['model_provider = '+json.dumps(provider),'cli_auth_credentials_store = "file"','[model_providers.'+json.dumps(provider)+']']
for key,value in source['model_providers'][provider].items():
 if not isinstance(value,(str,bool,int,float)): raise RuntimeError('Unsupported proxy config value')
 lines.append(json.dumps(key)+' = '+json.dumps(value))
root=pathlib.Path('/tmp/gate-config'); root.mkdir(exist_ok=True)
conf=root/'config.toml'; conf.write_text('\n'.join(lines)+'\n'); conf.chmod(0o444)
for name,target in [('config.toml',str(conf)),('auth.json','/home/agent/.codex/auth.json')]:
 link=state/name
 if link.is_symlink() or link.is_file(): link.unlink()
 elif link.exists(): raise RuntimeError('Invalid session config path')
 link.symlink_to(target)
'''
        self.checked([sbx_executable(),'exec','-u','root',self.name,'python3','-c',setup,
                      str(self.state),str(self.uid),str(self.gid)])
        self.version = self.checked([sbx_executable(),'exec',self.name,'codex','--version']).strip()
        sbx_check_network_policy(self.name)
        self.probe()
        self.overhead += time.monotonic()-started

    def probe(self):
        """Independent probe under exactly the UID/capability policy used by Codex."""
        code = r'''
import pathlib,os,json,subprocess,socket,sys,errno
lab,state=map(pathlib.Path,sys.argv[1:3]); readonly=sys.argv[3]=='True'
r={'uid':os.geteuid(),'status':pathlib.Path('/proc/self/status').read_text(),
   'mountinfo':pathlib.Path('/proc/self/mountinfo').read_text()}
r['lab_readable']=(lab/'lab.conf').is_file() and bool((lab/'lab.conf').read_bytes())
p=lab/('.gate-write-probe-'+str(os.getpid()))
try: p.write_text('probe'); p.unlink(); r['lab_writable']=True
except OSError as e: r['lab_writable']=False; r['lab_errno']=e.errno
p=state/'.state-probe'; p.write_text('ok'); p.unlink(); r['state_writable']=True
r['sudo_denied']=subprocess.run(['sudo','-n','true'],capture_output=True).returncode!=0
r['docker_sockets']={}
for path in ('/var/run/docker.sock','/run/docker.sock','/run/containerd/containerd.sock'):
 s=socket.socket(socket.AF_UNIX)
 try: s.connect(path); r['docker_sockets'][path]=True
 except OSError: r['docker_sockets'][path]=False
 finally: s.close()
r['docker_tcp']={}
for port in (2375,2376):
 s=socket.socket(); s.settimeout(.3)
 try: s.connect(('127.0.0.1',port)); r['docker_tcp'][str(port)]=True
 except OSError: r['docker_tcp'][str(port)]=False
 finally: s.close()
print(json.dumps(r))
'''
        data = json.loads(self.checked(self.prefix()+['python3','-c',code,str(self.workspace),str(self.state),str(self.readonly)]))
        status = data['status']
        secure = (data['uid'] != 0 and 'NoNewPrivs:\t1' in status and
                  all(f'{key}:\t0000000000000000' in status for key in ('CapEff','CapPrm','CapInh','CapAmb','CapBnd')) and
                  data['lab_readable'] and data['state_writable'] and data['sudo_denied'] and
                  not any(data['docker_sockets'].values()) and not any(data['docker_tcp'].values()) and
                  data['lab_writable'] == (not self.readonly))
        if self.readonly:
            secure = secure and data.get('lab_errno') == 30
        # The only host filesystem exports must be the state and current lab.
        exports = []
        for line in data['mountinfo'].splitlines():
            if ' - virtiofs host ' in line:
                exports.append(line.split()[4])
        secure = secure and set(exports) == {str(self.workspace), str(self.state)}
        servers = json.loads(self.checked(self.prefix()+['codex','mcp','list','--json']))
        secure = secure and isinstance(servers,list) and not any(s.get('enabled') for s in servers)
        self.checked(self.prefix()+['codex','login','status'])
        data['mcp_servers_enabled'] = [s.get('name') for s in servers if s.get('enabled')]
        data['secure'] = bool(secure)
        phase = 'protected' if self.readonly else 'writable'
        write_json(self.logs / f'isolation_{phase}.json',data)
        if not secure:
            raise SandboxProbeError('Gate isolation probe failed; see isolation_'+phase+'.json')

    def turn(self, *, prompt: bytes, directory: Path, timeout: int):
        """Persist exact UTF-8 stdin before starting; verify explicit thread ID."""
        from .codex_cli_runner import parse_events
        directory.mkdir(parents=True, exist_ok=False)
        (directory/'prompt_sent.md').write_bytes(prompt)
        if (directory/'prompt_sent.md').read_bytes() != prompt:
            raise SandboxArtifactError('Prompt changed before delivery')
        args = ['codex','exec'] + (['resume',self.thread_id] if self.thread_id else [])
        args += ['--json','--skip-git-repo-check','--disable','memories',
                 '-c','features.memories=false','-c','approval_policy="never"',
                 '-c','sandbox_mode='+json.dumps('read-only' if self.readonly else 'workspace-write'),
                 '-c','sandbox_workspace_write.writable_roots='+json.dumps([str(self.workspace),str(self.state)])]
        if self.config.model(): args += ['--model',self.config.model()]
        if self.config.reasoning_effort(): args += ['-c','model_reasoning_effort='+json.dumps(self.config.reasoning_effort())]
        args += ['-']
        # This trusted wrapper reports the actual pre-exec identity. exec cannot
        # regain privilege because every capability and no-new-privs are set.
        wrapper = "import os,pathlib,json,sys; print(json.dumps({'type':'skill_gate.process_attestation','uid':os.geteuid(),'status':pathlib.Path('/proc/self/status').read_text()}),flush=True); os.execvp(sys.argv[1],sys.argv[1:])"
        command = self.prefix()+['python3','-c',wrapper]+args
        self.commands.append(command)
        write_json(directory/'invocation.json',{'command':command,'stdin_bytes':len(prompt),
                  'stdin_sha256':__import__('hashlib').sha256(prompt).hexdigest(),'session_expected':self.thread_id})
        started=time.monotonic(); timed_out=False
        try:
            process=subprocess.run(command,input=prompt,capture_output=True,timeout=timeout,env=self.environment())
            out,err,code=process.stdout,process.stderr,process.returncode
        except subprocess.TimeoutExpired as e:
            out,err,code,timed_out=e.stdout or b'',e.stderr or b'',124,True
        duration=time.monotonic()-started
        (directory/'events.jsonl').write_bytes(out); (directory/'stderr.log').write_bytes(err)
        message,usage=parse_events(out.decode('utf-8',errors='replace'))
        result={'returncode':code,'timed_out':timed_out,'duration_seconds':duration,
                'usage':usage,'final_message':message,'stdin_delivery_verified':False}
        self.turns.append((directory,result))
        try:
            events=[json.loads(line) for line in out.decode('utf-8').splitlines() if line.strip()]
            if not events or events[0].get('type') != 'skill_gate.process_attestation' or events[0].get('uid') != self.uid:
                raise SandboxProbeError('Missing real process attestation')
            attestation=events[0]['status']
            if 'NoNewPrivs:\t1' not in attestation or any(f'{key}:\t0000000000000000' not in attestation for key in ('CapEff','CapPrm','CapBnd','CapAmb')):
                raise SandboxProbeError('Codex process privilege mismatch')
            ids=[e.get('thread_id') for e in events if e.get('type')=='thread.started']
            if code or timed_out or len(ids)!=1 or not isinstance(ids[0],str) or not ids[0]:
                raise SandboxExecutionError('Codex turn failed or missing thread ID')
            if self.thread_id is not None and ids[0]!=self.thread_id:
                raise SandboxExecutionError('Codex session continuity lost')
            self.thread_id=ids[0]
            if not any(e.get('type')=='turn.completed' for e in events) or any(e.get('type') in ('turn.failed','error') for e in events):
                raise SandboxExecutionError('Codex did not complete the turn')
            result['stdin_delivery_verified']=True; result['session_id']=self.thread_id
            return events,result
        except Exception as e:
            result['error']=str(e)
            raise
        finally:
            write_json(directory/'result.json',result)

    def close(self):
        if self.name:
            started=time.monotonic()
            name=self.name
            ok,error=_sbx_rm(name)
            self.cleanup.append({'name':name,'ok':ok,'error':error})
            self.overhead+=time.monotonic()-started
            if not ok: raise SandboxCleanupError(f'Gate cleanup failed: {error}')
            self.name=None
