"""Verifiche runtime senza avviare laboratori né chiamate ai modelli."""
import shutil
import subprocess
import sys
from pathlib import Path

from .agent_factory import validate_agent
from .config import verify_skills
from .correction_input import correction_path, validate_correction


def preflight(config, agent: str, skill_mode: str | None = None,
              scenario_ids: list[str] | tuple[str, ...] | None = None) -> None:
    if scenario_ids is None and hasattr(config, "root"):
        scenarios_root = config.root / "scenarios"
        scenario_ids = (sorted(path.name for path in scenarios_root.iterdir() if path.is_dir())
                        if scenarios_root.is_dir() else ())
    elif scenario_ids is None:
        scenario_ids = ()
    for scenario_id in scenario_ids:
        validate_correction(correction_path(config.root, scenario_id))
    verify_skills(config)
    validate_agent(agent)

    # Prerequisiti comuni: Docker, Kathara, checker.
    common_commands = [
        ["docker", "info"], ["docker", "compose", "version"],
        [sys.executable, "-m", "kathara_lab_checker", "--version"],
        [sys.executable, "-m", "kathara", "--version"],
    ]

    if agent == "codex":
        from .codex_cli_runner import codex_environment
        if skill_mode is not None:
            from .skill_modes import (
                ensure_no_external_skill_collisions,
                expand_skill_mode,
                validate_mode_sources,
            )
            ensure_no_external_skill_collisions(config.root)
            for mode in expand_skill_mode(skill_mode):
                validate_mode_sources(config, mode)
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
