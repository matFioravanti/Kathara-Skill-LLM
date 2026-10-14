"""Verifiche runtime senza avviare laboratori né chiamate ai modelli."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .agent_factory import validate_agent
from .correction_input import correction_path, validate_correction


def _is_docker_sandbox_backend(config) -> bool:
    """Restituisce True se execution_backend è 'docker_sandbox'."""
    return (
        config.data.get("docker_sandbox", {}).get("execution_backend") == "docker_sandbox"
    )


def parse_cli_version(output: str) -> str:
    match = re.search(r"(?:v)?(\d+\.\d+\.\d+(?:-\w+)?)", output)
    if not match:
        raise RuntimeError(f"Unable to parse valid version from output: {output!r}")
    return match.group(1)


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

    # --- Mode-aware skill verification ---
    # Only verify skills required by the actual mode and agent.
    # No global verify_skills() call: that would require all skills even in no_skill/dns_only.
    if agent == "codex":
        from .skill_modes import (
            ensure_no_external_skill_collisions,
            expand_skill_mode,
            validate_mode_sources,
        )
        ensure_no_external_skill_collisions(config.root)
        effective_modes = expand_skill_mode(skill_mode) if skill_mode is not None else ()
        for mode in effective_modes:
            validate_mode_sources(config, mode)
    elif agent == "antigravity":
        # Antigravity uses only the dns_skill; verify it if configured.
        from .config import verify_skills
        dns_configured = config.data.get("aut", {}).get("dns_skill")
        if dns_configured:
            verify_skills(config, ("kathara-dns",))
        else:
            raise RuntimeError(
                "La configurazione Antigravity richiede aut.dns_skill."
            )

    validate_agent(agent)

    # --- Docker Sandbox preflight (quando il backend è docker_sandbox) ---
    if agent == "codex" and _is_docker_sandbox_backend(config):
        from .docker_sandbox_runner import preflight_docker_sandbox, SandboxError
        ds_cfg = config.data.get("docker_sandbox", {})
        expected_sbx_ver = ds_cfg.get("sbx_version", "0.48.0")
        auto_start = bool(ds_cfg.get("auto_start_daemon", True))
        auto_start_docker = bool(ds_cfg.get("auto_start_docker", True))
        daemon_wait = int(ds_cfg.get("daemon_wait_seconds", 30))
        docker_wait = int(ds_cfg.get("docker_wait_seconds", 45))
        try:
            preflight_docker_sandbox(
                expected_sbx_version=expected_sbx_ver,
                auto_start_daemon=auto_start,
                auto_start_docker=auto_start_docker,
                daemon_wait_seconds=daemon_wait,
                docker_wait_seconds=docker_wait,
            )
        except SandboxError as exc:
            raise RuntimeError(str(exc)) from exc

    # Prerequisiti comuni: Docker, Kathara, checker.
    common_commands = [
        ["docker", "info"], ["docker", "compose", "version"],
        [sys.executable, "-m", "kathara_lab_checker", "--version"],
        [sys.executable, "-m", "kathara", "--version"],
    ]

    if agent == "codex":
        if _is_docker_sandbox_backend(config):
            from .docker_sandbox_runner import sbx_check_sandbox_codex, SandboxError
            ds_cfg = config.data.get("docker_sandbox", {})
            expected_version = ds_cfg.get("codex_version") or config.data.get("aut", {}).get("version")
            verify_in_sandbox = ds_cfg.get("verify_sandbox_codex", True)
            if verify_in_sandbox:
                try:
                    sbx_check_sandbox_codex(expected_version=expected_version)
                except SandboxError as exc:
                    raise RuntimeError(str(exc)) from exc
        else:
            from .codex_cli_runner import codex_environment
            
            expected_version = config.data.get("aut", {}).get("version")
            if not expected_version:
                raise RuntimeError("aut.version is missing from configuration.")
                
            codex = shutil.which("codex")
            if not codex:
                raise RuntimeError("Codex CLI non trovata nel PATH.")
                
            environment = codex_environment()
            
            version_result = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=30, env=environment)
            if version_result.returncode:
                raise RuntimeError(f"Prerequisito non disponibile: {codex} --version\n{version_result.stderr.strip()}")
                
            actual_version = parse_cli_version(version_result.stdout)
            if actual_version != expected_version:
                raise RuntimeError(
                    f"Codex CLI version mismatch:\n"
                    f"expected {expected_version}\n"
                    f"actual {actual_version}"
                )
                
            login_result = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=30, env=environment)
            if login_result.returncode:
                raise RuntimeError("Codex CLI is not authenticated. Run `codex` or `codex login` manually and authenticate with ChatGPT.")
            
    elif agent == "antigravity":
        expected_version = config.data.get("aut", {}).get("version")
        if not expected_version:
            raise RuntimeError("aut.version is missing from configuration.")
            
        agy = shutil.which("agy")
        if not agy:
            raise RuntimeError("Antigravity CLI (agy) non trovata nel PATH.")
            
        version_result = subprocess.run([agy, "--version"], capture_output=True, text=True, timeout=30)
        if version_result.returncode:
            raise RuntimeError(f"Prerequisito non disponibile: {agy} --version\n{version_result.stderr.strip()}")
            
        actual_version = parse_cli_version(version_result.stdout)
        if actual_version != expected_version:
            raise RuntimeError(
                f"Antigravity CLI version mismatch:\n"
                f"expected {expected_version}\n"
                f"actual {actual_version}"
            )

    for command in common_commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"Prerequisito non disponibile: {' '.join(command)}\n{result.stderr.strip()}")
