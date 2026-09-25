"""Modalità di disponibilità e uso esplicito delle Skill Codex."""
from dataclasses import dataclass
from pathlib import Path
import os
import shutil


@dataclass(frozen=True)
class SkillMode:
    available_skills: tuple[str, ...]
    forced_skills: tuple[str, ...]
    directive: str


SKILL_MODES = {
    "no_skill": SkillMode((), (), ""),
    "creation_only": SkillMode(
        ("kathara-creation",), ("kathara-creation",),
        "Use only $kathara-creation for this task.",
    ),
    "dns_only": SkillMode(
        ("kathara-dns",), ("kathara-dns",),
        "Use only $kathara-dns for this task.",
    ),
    "both_forced": SkillMode(
        ("kathara-creation", "kathara-dns"),
        ("kathara-creation", "kathara-dns"),
        "Use $kathara-creation and $kathara-dns for this task.",
    ),
    "auto": SkillMode(("kathara-creation", "kathara-dns"), (), ""),
}
SKILL_MODE_ORDER = tuple(SKILL_MODES)
SKILL_MODE_CHOICES = SKILL_MODE_ORDER

SKILL_CONFIG_KEYS = {
    "kathara-creation": "creation_skill",
    "kathara-dns": "dns_skill",
}


def mode_details(mode: str) -> SkillMode:
    try:
        return SKILL_MODES[mode]
    except KeyError as error:
        raise ValueError(f"Modalità Skill non valida: {mode}") from error


def expand_skill_mode(selection: str) -> tuple[str, ...]:
    """Espande l'orchestratore `all` in modalità effettive, nell'ordine definito."""
    if selection == "all":
        return SKILL_MODE_ORDER
    mode_details(selection)
    return (selection,)


def execute_skill_modes(selection: str, callback):
    """Chiama callback in serie e produce i risultati senza accodare/stagiare batch."""
    modes = expand_skill_mode(selection)
    for index, mode in enumerate(modes, start=1):
        yield mode, index, len(modes), callback(mode, index, len(modes))


def execution_prompt(mode: str, original_prompt: str) -> str:
    """Restituisce direttiva minima + prompt originale, senza riscriverlo."""
    details = mode_details(mode)
    if not details.directive:
        return original_prompt
    return f"{details.directive}\n\n{original_prompt}"


def source_paths(config, skills: tuple[str, ...]) -> dict[str, Path]:
    paths = {}
    for name in skills:
        key = SKILL_CONFIG_KEYS[name]
        configured = config.data["aut"].get(key)
        if not configured:
            raise ValueError(f"Percorso della Skill {name} non configurato in aut.{key}.")
        source = config.path(configured)
        if source.is_symlink() or not source.is_file() or source.name != "SKILL.md":
            raise ValueError(
                f"Skill {name} non trovata o non valida: {source}. "
                "Aggiungi il suo SKILL.md canonico nel percorso configurato."
            )
        paths[name] = source
    return paths


def validate_mode_sources(config, mode: str) -> SkillMode:
    details = mode_details(mode)
    sources = source_paths(config, details.available_skills)
    from .skill_loader import load_skill

    for name, source in sources.items():
        if source.parent.is_symlink() or any(path.is_symlink() for path in source.parent.rglob("*")):
            raise ValueError(f"La Skill {name} contiene link simbolici e non può essere isolata: {source.parent}")
        skill = load_skill(source)
        if skill.name != name:
            raise ValueError(
                f"La Skill in {source} dichiara name={skill.name!r}; "
                f"per questa modalità deve dichiarare name={name!r}."
            )
    return details


def prepare_skill_workspace(workspace: Path, config, mode: str) -> SkillMode:
    """Pulisce e ricrea .codex/skills con esattamente le Skill disponibili."""
    details = mode_details(mode)
    workspace = workspace.resolve()
    codex_dir = workspace / ".codex"
    if codex_dir.is_symlink():
        raise ValueError(f"Directory Codex nel workspace non può essere un link: {codex_dir}")
    skill_dir = codex_dir / "skills"
    if skill_dir.is_symlink():
        raise ValueError(f"Directory Skill nel workspace non può essere un link: {skill_dir}")
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    skill_dir.mkdir(parents=True)

    sources = source_paths(config, details.available_skills)
    validate_mode_sources(config, mode)
    for name, source in sources.items():
        shutil.copytree(source.parent, skill_dir / name, symlinks=True)
    return details


def _matching_skill_files(skill_root: Path, *, recursive: bool = False) -> list[Path]:
    if not skill_root.is_dir() or skill_root.is_symlink():
        return []
    pattern = "**/SKILL.md" if recursive else "*/SKILL.md"
    return [path for path in skill_root.glob(pattern) if path.is_file()]


def find_external_skill_collisions(project_root: Path, *, environ: dict[str, str] | None = None) -> list[tuple[str, Path]]:
    """Trova kathara-* in scope utente o .codex/skills antenati del workspace."""
    env = os.environ if environ is None else environ
    codex_home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    roots = {
        (codex_home / "skills", True),
        (codex_home / "plugins" / "cache", True),
    }
    current = project_root.resolve()
    for directory in (current, *current.parents):
        roots.add((directory / ".codex" / "skills", False))
        roots.add((directory / ".codex" / "plugins", True))

    collisions = []
    seen = set()
    for root, recursive in sorted(roots, key=lambda value: str(value[0])):
        for skill_file in _matching_skill_files(root, recursive=recursive):
            skill_file = skill_file.resolve()
            if skill_file in seen:
                continue
            seen.add(skill_file)
            name = skill_file.parent.name
            try:
                from .skill_loader import load_skill
                declared_name = load_skill(skill_file).name
            except Exception:
                declared_name = None
            if name in SKILL_CONFIG_KEYS or declared_name in SKILL_CONFIG_KEYS:
                collisions.append((name if name in SKILL_CONFIG_KEYS else declared_name, skill_file))
    return collisions


def ensure_no_external_skill_collisions(project_root: Path, *, environ: dict[str, str] | None = None) -> None:
    collisions = find_external_skill_collisions(project_root, environ=environ)
    if collisions:
        entries = "\n".join(f"- {name}: {path}" for name, path in collisions)
        raise RuntimeError(
            "Skill Kathara omonime fuori dal workspace contaminerebbero l'esperimento. "
            "Rimuovile o rinominale prima di continuare:\n" + entries
        )
