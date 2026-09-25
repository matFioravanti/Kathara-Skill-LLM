"""Copie, hash senza dereferenziare link e metadata atomici."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import stat


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def manifest(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Lab non valido: {root}")
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(base) / name
            info = path.lstat()
            entry = {"mode": stat.S_IMODE(info.st_mode)}
            if path.is_symlink():
                entry.update(kind="link", target=os.readlink(path))
            elif path.is_dir():
                entry.update(kind="directory")
            elif path.is_file():
                entry.update(kind="file", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                raise ValueError(f"File speciale non supportato: {path}")
            result[path.relative_to(root).as_posix()] = entry
    return result


def tree_hash(root: Path) -> str:
    return hashlib.sha256(json.dumps(manifest(root), sort_keys=True).encode()).hexdigest()


def copy_lab(source: Path, target: Path) -> None:
    # Nessun link può far leggere/scrivere file esterni durante la copia o il checker.
    if any(entry["kind"] == "link" for entry in manifest(source).values()):
        raise ValueError(f"Link simbolici non supportati nel laboratorio: {source}")
    shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)


def component_versions() -> dict:
    return {name: importlib.metadata.version(name) for name in
            ("inspect-ai", "inspect-swe", "kathara-lab-checker", "kathara", "pandas", "PyYAML", "openai")}


def allocate_run_directory(runs: Path, scenario_id: str, prompt_type: str, skill_mode: str) -> tuple[Path, int]:
    """Alloca atomicamente il prossimo rNNN per scenario e modalità."""
    mode_root = runs / scenario_id / prompt_type / skill_mode
    mode_root.mkdir(parents=True, exist_ok=True)
    existing = [
        int(match.group(1))
        for path in mode_root.iterdir()
        if path.is_dir() and (match := re.fullmatch(r"r(\d{3,})", path.name))
    ]
    run_number = max(existing, default=0) + 1
    while True:
        run = mode_root / f"r{run_number:03d}"
        try:
            run.mkdir(exist_ok=False)
            return run, run_number
        except FileExistsError:
            run_number += 1


def logical_run_id(scenario_id: str, prompt_type: str, skill_mode: str, run_number: int) -> str:
    return f"{scenario_id}__{prompt_type}__{skill_mode}__r{run_number:03d}"


def create_workspace(runs: Path, scenario, prompt_type: str, skill_mode: str, prompt: str) -> Path:
    run, _ = allocate_run_directory(runs, scenario.scenario_id, prompt_type, skill_mode)
    for folder in ("input", "lab", "logs/aut", "logs/generator", "results"):
        (run / folder).mkdir(parents=True, exist_ok=False)
    # input/lab: copia immutabile del baseline originale
    copy_lab(scenario.lab, run / "input/lab")
    # input/prompt.md: prompt originale per riferimento
    (run / "input/prompt.md").write_text(prompt, encoding="utf-8")
    # lab/: unica copia modificabile — l'AUT lavora qui
    copy_lab(scenario.lab, run / "lab")
    return run
