"""Esegue la Codex CLI dell'host senza provider API o sandbox Inspect."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
import subprocess
import time
from typing import Any

from .workspace import write_json


class CodexExecutionError(RuntimeError):
    """Errore tecnico della CLI: non esiste alcun fallback verso provider API."""


@dataclass(frozen=True)
class CodexRun:
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


def codex_environment() -> dict[str, str]:
    """Preserva login locale/CODEX_HOME ma impedisce la selezione via API key."""
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)
    return env


def codex_executable() -> str:
    executable = shutil.which("codex")
    if not executable:
        raise CodexExecutionError("Codex CLI non trovata nel PATH.")
    return executable


def command_for(*, workspace: Path, model: str | None, reasoning_effort: str | None) -> tuple[str, ...]:
    command = [codex_executable(), "exec", "--json", "--ephemeral", "--sandbox", "workspace-write",
               "--skip-git-repo-check", "-C", str(workspace.resolve())]
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append("-")
    return tuple(command)


def parse_events(stdout: str) -> tuple[str | None, dict[str, Any] | None]:
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


def run_codex(*, prompt: str, workspace: Path, logs: Path, timeout: int,
              model: str | None, reasoning_effort: str | None, variant: str) -> CodexRun:
    """Invoca `codex exec -` sull'host e conserva i byte testuali nativi JSONL."""
    if not workspace.is_dir():
        raise CodexExecutionError(f"Workspace Codex non trovato: {workspace}")
    logs.mkdir(parents=True, exist_ok=True)
    command = command_for(workspace=workspace, model=model, reasoning_effort=reasoning_effort)
    started = time.monotonic()
    try:
        completed = subprocess.run(command, input=prompt, text=True, capture_output=True, cwd=workspace,
                                   env=codex_environment(), timeout=timeout, check=False)
        stdout, stderr, returncode, timed_out = completed.stdout or "", completed.stderr or "", completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr += f"\nCodex timed out after {timeout}s.\n"
        returncode, timed_out = 124, True
    duration = time.monotonic() - started
    final_message, usage = parse_events(stdout)
    (logs / "events.jsonl").write_text(stdout, encoding="utf-8")
    (logs / "stderr.log").write_text(stderr, encoding="utf-8")
    (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
    result = CodexRun(command, returncode, stdout, stderr, duration, timed_out, final_message, usage)
    write_json(logs / "invocation.json", {
        "command": list(command), "cwd": str(workspace.resolve()), "variant": variant,
        "execution_backend": "codex_cli", "authentication": "local_chatgpt_login", "api_key_used": False,
        "model": model, "reasoning_effort": reasoning_effort,
    })
    write_json(logs / "result.json", {
        "returncode": returncode, "timed_out": timed_out, "duration_seconds": duration,
        "final_message": final_message, "usage": usage,
    })
    if not result.success:
        detail = stderr.strip() or "nessun dettaglio in stderr"
        raise CodexExecutionError(f"Codex CLI fallita (exit {returncode}): {detail}")
    return result
