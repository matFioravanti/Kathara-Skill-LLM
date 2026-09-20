"""Valida il frontmatter delle skill prima di passarne i percorsi a Codex CLI."""
from pathlib import Path

import yaml
from inspect_ai.tool import Skill


def load_skill(path: Path) -> Skill:
    # read_skills(directory) impone name == directory.name; lab_checker contiene
    # un underscore non ammesso nel nome skill. Skill è l'alternativa pubblica
    # che preserva nome e contenuto originali senza rinominare la directory.
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if not text.startswith("---") or len(parts) != 3:
        raise ValueError(f"Frontmatter name/description mancante: {path}")
    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter non valido: {path}")
    # `argument-hint` e `user-invocable` sono estensioni del catalogo Codex.
    # L'oggetto Skill locale le omette soltanto nella validazione; la CLI legge
    # direttamente il file indicato nel prompt, senza creare CODEX_HOME.
    inspect_fields = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    allowed = inspect_fields | {"argument-hint", "user-invocable"}
    if frontmatter.keys() - allowed:
        raise ValueError(f"Campi skill non supportati: {frontmatter.keys() - allowed}")
    resources = {}
    for kind in ("scripts", "references", "assets"):
        directory = path.parent / kind
        resources[kind] = {p.relative_to(directory).as_posix(): p.resolve()
                           for p in directory.rglob("*") if p.is_file()
                           and not any(x.startswith((".", "_")) for x in p.relative_to(directory).parts)}
    inspect_frontmatter = {key: value for key, value in frontmatter.items() if key in inspect_fields}
    return Skill(**inspect_frontmatter, instructions=parts[2].lstrip("\n"), **resources)
