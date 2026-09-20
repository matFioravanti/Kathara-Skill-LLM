"""Compatibilità del nome modulo: l'AUT ora usa Codex CLI direttamente sull'host."""
from pathlib import Path

from .agent_factory import validate_agent
from .codex_cli_runner import run_codex


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
    run_codex(prompt=prompt, workspace=lab, logs=run / "logs/aut",
              timeout=config.data["benchmark"]["timeout_seconds"], model=config.model(),
              reasoning_effort=config.reasoning_effort(), variant="aut")
    return run / "logs/aut/events.jsonl"
