"""Esecuzione dell'AUT host e generazione del log di telemetria Inspect AI."""
from pathlib import Path

from .agent_factory import validate_agent
from .antigravity_cli_runner import run_antigravity
from .codex_cli_runner import run_codex
from .inspect_adapter import create_inspect_eval_log


def run_aut(config, scenario, run: Path, agent: str) -> Path:
    validate_agent(agent)
    lab = run / "lab"
    skill = config.path(config.data["aut"]["dns_skill"])
    prompt = (
        f"Configura direttamente i file del laboratorio nella directory corrente {lab}. "
        f"Leggi e segui la skill DNS in {skill}. Non produrre JSON di modifiche, non delegare a Python "
        "la scrittura dei file e non generare correction.yaml. Non avviare Kathara: "
        "il laboratorio sarà avviato dal checker dopo questa chiamata.\n\n"
        "REQUISITI ORIGINALI:\n" + scenario.prompt
    )
    aut_logs = run / "logs/aut"
    if agent == "codex":
        run_codex(
            prompt=prompt,
            workspace=lab,
            logs=aut_logs,
            timeout=config.data["benchmark"]["timeout_seconds"],
            model=config.model(),
            reasoning_effort=config.reasoning_effort(),
            variant="aut",
        )
    elif agent == "antigravity":
        run_antigravity(
            prompt=prompt,
            workspace=lab,
            logs=aut_logs,
            timeout=config.data["benchmark"]["timeout_seconds"],
            model=config.model(),
            reasoning_effort=config.reasoning_effort(),
            variant="aut",
        )

    # Step di telemetria Inspect AI: crea il log .eval nativo senza alterare l'esito dell'AUT
    eval_log_path = create_inspect_eval_log(
        logs=aut_logs,
        run_id=run.name,
        prompt=prompt,
        agent=agent,
        model=config.model(),
    )
    return eval_log_path or (aut_logs / "events.jsonl")
