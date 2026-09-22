"""Esegue la Antigravity CLI dell'host per l'integrazione nel benchmark."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
import subprocess
import time
from typing import Any

from .workspace import write_json


class AntigravityExecutionError(RuntimeError):
    """Errore tecnico della CLI di Antigravity."""


@dataclass(frozen=True)
class AntigravityRun:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    final_message: str | None
    usage: dict[str, Any] | None

    @property
    def success(self) -> bool:
        return not self.timed_out and self.returncode == 0


def antigravity_environment() -> dict[str, str]:
    """Preserva l'ambiente locale ma impedisce conflitti con API key se presenti."""
    env = os.environ.copy()
    # Rimuoviamo eventuali chiavi API se vogliamo forzare l'uso dell'autenticazione locale Google,
    # analogamente a quanto fatto per Codex.
    env.pop("GEMINI_API_KEY", None)
    return env


def antigravity_executable() -> str:
    executable = shutil.which("agy")
    if not executable:
        raise AntigravityExecutionError("Antigravity CLI (agy) non trovata nel PATH.")
    return executable


def command_for(*, workspace: Path, model: str | None, reasoning_effort: str | None, prompt: str) -> tuple[str, ...]:
    command = [
        antigravity_executable(),
        "--add-dir", str(workspace.resolve()),
        "--dangerously-skip-permissions",
        "--output-format", "stream-json"
    ]
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["--effort", reasoning_effort])
    command.extend(["--print", prompt])
    return tuple(command)


def parse_events(stdout: str) -> tuple[str | None, dict[str, Any] | None]:
    final_message = None
    usage = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "result" and isinstance(event.get("result"), dict):
            res = event["result"]
            if res.get("status") == "SUCCESS":
                final_message = res.get("response")
                usage = res.get("usage")
    return final_message, usage


def run_antigravity(*, prompt: str, workspace: Path, logs: Path, timeout: int,
                    model: str | None, reasoning_effort: str | None, variant: str) -> AntigravityRun:
    """Invoca la CLI `agy` sull'host e conserva i byte testuali nativi JSONL."""
    if not workspace.is_dir():
        raise AntigravityExecutionError(f"Workspace Antigravity non trovato: {workspace}")
    logs.mkdir(parents=True, exist_ok=True)
    command = command_for(workspace=workspace, model=model, reasoning_effort=reasoning_effort, prompt=prompt)
    started = time.monotonic()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, cwd=workspace,
                                   env=antigravity_environment(), timeout=timeout, check=False)
        stdout, stderr, returncode, timed_out = completed.stdout or "", completed.stderr or "", completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr += f"\nAntigravity timed out after {timeout}s.\n"
        returncode, timed_out = 124, True
    
    duration = time.monotonic() - started
    final_message, usage = parse_events(stdout)
    (logs / "events.jsonl").write_text(stdout, encoding="utf-8")
    (logs / "stderr.log").write_text(stderr, encoding="utf-8")
    (logs / "prompt.txt").write_text(prompt, encoding="utf-8")
    
    result = AntigravityRun(command, returncode, stdout, stderr, duration, timed_out, final_message, usage)
    write_json(logs / "invocation.json", {
        "command": list(command), "cwd": str(workspace.resolve()), "variant": variant,
        "execution_backend": "antigravity_cli", "authentication": "local_google_login", "api_key_used": False,
        "model": model, "reasoning_effort": reasoning_effort,
    })
    write_json(logs / "result.json", {
        "returncode": returncode, "timed_out": timed_out, "duration_seconds": duration,
        "final_message": final_message, "usage": usage,
    })
    
    if not result.success:
        detail = stderr.strip() or "nessun dettaglio in stderr"
        raise AntigravityExecutionError(f"Antigravity CLI fallita (exit {returncode}): {detail}")
    return result
