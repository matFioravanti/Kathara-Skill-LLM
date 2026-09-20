"""Copie, hash senza dereferenziare link e metadata atomici."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import uuid


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


def create_workspace(runs: Path, scenario, agent: str, repetition: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run = runs / f"{scenario.scenario_id}__{agent}__r{repetition:03d}__{stamp}_{uuid.uuid4().hex[:8]}"
    for folder in ("input", "lab", "logs/aut", "logs/generator", "results"):
        (run / folder).mkdir(parents=True, exist_ok=False)
    # input/lab: copia immutabile del baseline originale
    copy_lab(scenario.lab, run / "input/lab")
    # input/prompt.md: prompt originale per riferimento
    (run / "input/prompt.md").write_text(scenario.prompt, encoding="utf-8")
    # lab/: unica copia modificabile — l'AUT lavora qui
    copy_lab(scenario.lab, run / "lab")
    return run
