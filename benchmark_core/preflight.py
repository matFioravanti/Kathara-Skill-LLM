"""Verifiche runtime senza avviare laboratori né chiamate ai modelli."""
import shutil
import subprocess
import sys
from pathlib import Path

from .agent_factory import validate_agent
from .config import verify_skills


def preflight(config, agent: str) -> None:
    paths = verify_skills(config)
    validate_agent(agent)

    # Prerequisiti comuni: Docker, Kathara, checker.
    common_commands = [
        ["docker", "info"], ["docker", "compose", "version"],
        [sys.executable, "-m", "kathara_lab_checker", "--version"],
        [sys.executable, "-m", "kathara", "--version"],
    ]

    if agent == "codex":
        from .codex_cli_runner import codex_environment
        codex = shutil.which("codex")
        if not codex:
            raise RuntimeError("Codex CLI non trovata nel PATH.")
        environment = codex_environment()
        agent_commands = [[codex, "--version"], [codex, "login", "status"]]
        for command in agent_commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=environment)
            if result.returncode:
                if command[1:] == ["login", "status"]:
                    raise RuntimeError("Codex CLI is not authenticated. Run `codex` or `codex login` manually and authenticate with ChatGPT.")
                raise RuntimeError(f"Prerequisito non disponibile: {' '.join(command)}\n{result.stderr.strip()}")
    elif agent == "antigravity":
        agy = shutil.which("agy")
        if not agy:
            raise RuntimeError("Antigravity CLI (agy) non trovata nel PATH.")
        result = subprocess.run([agy, "--version"], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"Prerequisito non disponibile: {agy} --version\n{result.stderr.strip()}")

    for command in common_commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"Prerequisito non disponibile: {' '.join(command)}\n{result.stderr.strip()}")
