"""Esecuzione dell'AUT host e generazione del log di telemetria Inspect AI."""
from pathlib import Path

import subprocess
import shutil
import tempfile

from .agent_factory import validate_agent
from .antigravity_cli_runner import run_antigravity
from .codex_cli_runner import run_codex
from .inspect_adapter import create_inspect_eval_log
from .skill_modes import execution_prompt, prepare_skill_workspace


def validate_aut_workspace_isolation(workspace: Path, config_root: Path):
    if workspace.is_relative_to(config_root):
        raise RuntimeError(f"AUT workspace {workspace} is still inside config root {config_root}")
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=True
        )
        git_root = Path(res.stdout.strip()).resolve()
        if git_root == config_root.resolve():
            raise RuntimeError("AUT workspace leaks into the main Git repository")
    except subprocess.CalledProcessError:
        pass


def run_aut(config, scenario, run: Path, agent: str, original_prompt: str, skill_mode: str | None = None,
            run_id: str | None = None) -> Path:
    validate_agent(agent)
    persistent_lab = run / "lab"
    aut_logs = run / "logs/aut"
    
    with tempfile.TemporaryDirectory(prefix="kathara-aut-") as temp_dir:
        temp_lab = Path(temp_dir) / "lab"
        shutil.copytree(persistent_lab, temp_lab)
        validate_aut_workspace_isolation(temp_lab, config.root)
        prompt = ""
        
        try:
            if agent == "codex":
                skill_mode = skill_mode or "dns_only"
                prepare_skill_workspace(temp_lab, config, skill_mode)
                prompt = execution_prompt(skill_mode, original_prompt)
                run_codex(
                    prompt=prompt,
                    workspace=temp_lab,
                    logs=aut_logs,
                    timeout=config.data["benchmark"]["timeout_seconds"],
                    model=config.model(),
                    reasoning_effort=config.reasoning_effort(),
                    variant="aut",
                )
            elif agent == "antigravity":
                skill = config.path(config.data["aut"]["dns_skill"])
                prompt = (
                    f"Configura direttamente i file del laboratorio nella directory corrente {temp_lab}. "
                    f"Leggi e segui la skill DNS in {skill}. Non produrre JSON di modifiche, non delegare a Python "
                    "la scrittura dei file e non generare correction.yaml. Non avviare Kathara: "
                    "il laboratorio sarà avviato dal checker dopo questa chiamata.\n\n"
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
        finally:
            if persistent_lab.exists():
                shutil.rmtree(persistent_lab)
            shutil.copytree(temp_lab, persistent_lab)

    # Step di telemetria Inspect AI: crea il log .eval nativo senza alterare l'esito dell'AUT
    eval_log_path = create_inspect_eval_log(
        logs=aut_logs,
        run_id=run_id or run.name,
        prompt=prompt,
        agent=agent,
        model=config.model(),
    )
    return eval_log_path or (aut_logs / "events.jsonl")
