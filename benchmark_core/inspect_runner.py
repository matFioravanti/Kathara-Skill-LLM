"""Esecuzione dell'AUT host e generazione del log di telemetria Inspect AI."""
from pathlib import Path

import inspect
import shutil
import subprocess
import sys
import tempfile

from .agent_factory import validate_agent
from .antigravity_cli_runner import run_antigravity
from .codex_cli_runner import run_codex
from .inspect_adapter import create_inspect_eval_log
from .skill_modes import execution_prompt, prepare_skill_workspace


def _call_runner(fn, **kwargs):
    """Invoca il runner filtrando gli argomenti se il target è un mock con parametri ristretti."""
    target = getattr(fn, "side_effect", None)
    if not callable(target):
        target = fn
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        sig = None
    if sig is not None and not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters and
                  sig.parameters[k].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
    return fn(**kwargs)


def _use_docker_sandbox(config) -> bool:
    """True se il backend configurato e' docker_sandbox."""
    return (
        config.data.get("docker_sandbox", {}).get("execution_backend") == "docker_sandbox"
    )


def validate_aut_workspace_isolation(workspace: Path, config_root: Path):
    if workspace.is_relative_to(config_root):
        raise RuntimeError(f"AUT workspace {workspace} is still inside config root {config_root}")
    try:
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=True
        )
        # Se ha successo, significa che workspace è in UN repository Git, non va bene
        raise RuntimeError(f"AUT workspace {workspace} is inside a Git repository. It must be completely isolated.")
    except subprocess.CalledProcessError:
        # Expected: it's not a git repository
        pass


def run_aut(config, scenario, run: Path, agent: str, original_prompt: str, skill_mode: str | None = None,
            run_id: str | None = None) -> Path:
    validate_agent(agent)
    from .skill_gate import enforce_or_block
    enforce_or_block(config, run, agent, skill_mode or ("dns_only" if agent == "codex" else "no_skill"))
    persistent_lab = run / "lab"
    aut_logs = run / "logs/aut"
    
    with tempfile.TemporaryDirectory(prefix="kathara-aut-") as temp_dir:
        temp_lab = Path(temp_dir) / "lab"
        shutil.copytree(persistent_lab, temp_lab)
        validate_aut_workspace_isolation(temp_lab, config.root)
        prompt = ""
        aut_error = None
        sync_error = None
        
        telemetry_cfg = config.sampling_telemetry_config() if hasattr(config, "sampling_telemetry_config") else {"enabled": False, "mode": "passive"}
        sampling_mode = str(telemetry_cfg.get("mode", "passive")) if telemetry_cfg.get("enabled") else "disabled"

        try:
            if agent == "codex":
                skill_mode = skill_mode or "dns_only"
                prepare_skill_workspace(temp_lab, config, skill_mode)
                prompt = execution_prompt(skill_mode, original_prompt)
                from .skill_gate import recovery_enabled, run_recovery_gate
                from .skill_modes import mode_details
                if recovery_enabled(config) and mode_details(skill_mode).forced_skills:
                    prompt = original_prompt
                    run_recovery_gate(config=config, run=run, workspace=temp_lab,
                                      original_prompt=original_prompt, mode=skill_mode)
                elif _use_docker_sandbox(config):
                    from .docker_sandbox_runner import (
                        _unique_sandbox_name,
                        run_codex_in_sandbox,
                    )
                    # Ricava run_number dall'ultimo componente del path run (rNNN)
                    try:
                        run_number = int(run.name[1:])
                    except (ValueError, IndexError):
                        run_number = 1
                    scenario_id = run.parents[2].name  # runs/<scenario>/<prompt>/<mode>/rNNN
                    sandbox_name = _unique_sandbox_name(scenario_id, run_number)
                    codex_sbx_kwargs = {
                        "prompt": prompt,
                        "workspace": temp_lab,
                        "logs": aut_logs,
                        "timeout": config.data["benchmark"]["timeout_seconds"],
                        "model": config.model(),
                        "reasoning_effort": config.reasoning_effort(),
                        "variant": "aut",
                        "sandbox_name": sandbox_name,
                        "codex_host_version": config.data.get("aut", {}).get("version"),
                        "auto_start_daemon": bool(
                            config.data.get("docker_sandbox", {}).get("auto_start_daemon", True)
                        ),
                        "daemon_wait_seconds": int(
                            config.data.get("docker_sandbox", {}).get("daemon_wait_seconds", 30)
                        ),
                        "sampling_mode": sampling_mode,
                    }
                    _call_runner(run_codex_in_sandbox, **codex_sbx_kwargs)
                else:
                    codex_kwargs = {
                        "prompt": prompt,
                        "workspace": temp_lab,
                        "logs": aut_logs,
                        "timeout": config.data["benchmark"]["timeout_seconds"],
                        "model": config.model(),
                        "reasoning_effort": config.reasoning_effort(),
                        "variant": "aut",
                        "sampling_mode": sampling_mode,
                    }
                    _call_runner(run_codex, **codex_kwargs)
            elif agent == "antigravity":
                original_skill = config.path(config.data["aut"]["dns_skill"])
                temp_skill_dir = Path(temp_dir) / "antigravity_skills"
                temp_skill_dir.mkdir(parents=True, exist_ok=True)
                temp_skill = temp_skill_dir / "SKILL.md"
                shutil.copy2(original_skill, temp_skill)

                prompt = (
                    f"Configura direttamente i file del laboratorio nella directory corrente {temp_lab}. "
                    f"Leggi e segui la skill DNS in {temp_skill}. Non produrre JSON di modifiche, non delegare a Python "
                    "la scrittura dei file e non generare correction.yaml. Non avviare Kathara: "
                    "il laboratorio sara' avviato dal checker dopo questa chiamata.\n\n"
                    "REQUISITI ORIGINALI:\n" + original_prompt
                )
                run_antigravity(
                    prompt=prompt,
                    workspace=temp_lab,
                    logs=aut_logs,
                    timeout=config.data["benchmark"]["timeout_seconds"],
                    model=config.model(),
                    reasoning_effort=config.reasoning_effort(),
                    variant="aut",
                )
        except BaseException as exc:
            aut_error = exc
        finally:
            from .sampling_telemetry import extract_sampling_telemetry, save_sampling_telemetry
            if not (aut_logs / "sampling_telemetry.json").exists():
                try:
                    telemetry = extract_sampling_telemetry(
                        aut_logs,
                        collection_mode=sampling_mode,
                        backend="docker_sandbox" if _use_docker_sandbox(config) else f"{agent}_cli",
                    )
                    save_sampling_telemetry(aut_logs, telemetry)
                except Exception:
                    pass

            try:
                codex_dir = temp_lab / ".codex"
                if codex_dir.is_symlink():
                    codex_dir.unlink()
                elif codex_dir.exists():
                    shutil.rmtree(codex_dir, ignore_errors=True)

                staging_lab = run / "lab.sync-tmp"
                if staging_lab.exists():
                    shutil.rmtree(staging_lab, ignore_errors=True)
                from .workspace import copy_lab
                copy_lab(temp_lab, staging_lab)
                
                if persistent_lab.exists():
                    shutil.rmtree(persistent_lab)
                staging_lab.rename(persistent_lab)
            except BaseException as exc:
                sync_error = exc

            # Step di telemetria Inspect AI: garantito anche in caso di errore AUT o sincronizzazione
            try:
                create_inspect_eval_log(
                    logs=aut_logs,
                    run_id=run_id or run.name,
                    prompt=prompt,
                    agent=agent,
                    model=config.model(),
                )
            except Exception as exc:
                print(f"Avviso telemetria Inspect su {run_id or run.name}: {exc}", file=sys.stderr)

            # Preserva e propaga l'errore senza che la telemetria lo nasconda
            if aut_error is not None:
                if sync_error is not None:
                    print(
                        f"Avviso: fallita anche la sincronizzazione lab su {run_id or run.name}: {sync_error}",
                        file=sys.stderr,
                    )
                raise aut_error
            if sync_error is not None:
                raise sync_error

    eval_path = aut_logs / f"{run_id or run.name}.eval"
    return eval_path if eval_path.exists() else (aut_logs / "events.jsonl")
