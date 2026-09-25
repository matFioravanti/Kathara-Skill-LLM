"""Risoluzione e validazione centralizzata dei prompt sperimentali."""
from pathlib import Path

PROMPT_TYPES = ("T1", "T2", "T3", "T4", "T5", "T6")


def resolve_prompt(root: Path, scenario_id: str, prompt_type: str) -> Path:
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"prompt_type non valido: {prompt_type!r}; valori ammessi: {', '.join(PROMPT_TYPES)}")
    scenario_dir = root / "prompt" / scenario_id
    if not scenario_dir.is_dir():
        raise ValueError(f"Directory prompt dello scenario '{scenario_id}' non trovata: {scenario_dir.relative_to(root)}")
    path = scenario_dir / f"{prompt_type}.md"
    if not path.is_file():
        raise ValueError(f"Missing prompt for scenario '{scenario_id}':\n{path.relative_to(root)}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Prompt non leggibile per scenario '{scenario_id}': {path.relative_to(root)} ({exc})") from exc
    if not content.strip():
        raise ValueError(f"Prompt vuoto per scenario '{scenario_id}': {path.relative_to(root)}")
    return path


def missing_prompts(root: Path, scenario_ids, prompt_type: str) -> list[str]:
    missing = []
    for scenario_id in scenario_ids:
        try:
            resolve_prompt(root, scenario_id, prompt_type)
        except ValueError:
            missing.append(f"prompt/{scenario_id}/{prompt_type}.md")
    return missing
