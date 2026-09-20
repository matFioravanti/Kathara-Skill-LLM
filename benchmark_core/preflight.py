"""Verifiche runtime senza avviare laboratori né chiamate ai modelli."""
import shutil
import subprocess
import sys
from pathlib import Path

from .agent_factory import validate_agent
from .codex_cli_runner import codex_environment
from .config import verify_skills


def preflight(config, agent: str) -> None:
    paths = verify_skills(config)
    validate_agent(agent)
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI non trovata nel PATH.")
    environment = codex_environment()
    for command in ([codex, "--version"], [codex, "login", "status"],
                    ["docker", "info"], ["docker", "compose", "version"],
                    [sys.executable, "-m", "kathara_lab_checker", "--version"],
                    [sys.executable, "-m", "kathara", "--version"]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=environment)
        if result.returncode:
            if command[1:] == ["login", "status"]:
                raise RuntimeError("Codex CLI is not authenticated. Run `codex` or `codex login` manually and authenticate with ChatGPT.")
            raise RuntimeError(f"Prerequisito non disponibile: {' '.join(command)}\n{result.stderr.strip()}")
