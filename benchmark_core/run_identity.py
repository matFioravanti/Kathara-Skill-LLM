"""Readable identities for observations and their physical executions.

The directory counter is local to an experimental cell. Never infer a
statistical replicate from that counter, including for historical manifests.
"""
from pathlib import Path
from urllib.parse import quote
import json


def observation_id(metadata: dict) -> str | None:
    replicate = metadata.get("replicate")
    lab = metadata.get("lab_id") or metadata.get("scenario_id") or metadata.get("scenario")
    if type(replicate) is not int or replicate < 1 or not lab:
        return None
    parts = [metadata.get("experiment_id") or "@legacy", lab]
    parts.extend(metadata.get(key) or "-" for key in ("dns_tree_id", "task_level", "prompt_type", "skill_mode"))
    return ":".join(quote(str(part), safe="_-.") for part in parts) + f":rep{replicate:03d}"


def identity_fields(metadata: dict) -> dict:
    observation = observation_id(metadata)
    number = metadata.get("run_number")
    execution = (f"{observation}:r{number:03d}"
                 if observation and type(number) is int and number > 0 else None)
    return {"observation_id": observation, "execution_id": execution}


def cell_metadata(cell) -> dict:
    return {"experiment_id": cell.experiment_id, "lab_id": cell.lab_id,
            "dns_tree_id": cell.dns_tree_id, "task_level": cell.task_level,
            "prompt_type": cell.prompt_type, "skill_mode": cell.skill_mode,
            "replicate": cell.replicate}


def describe_run(run: Path) -> str:
    """Derive a label for old and new runs without rewriting any manifest."""
    try:
        metadata = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return str(run)
    return identity_fields(metadata)["execution_id"] or str(run)
