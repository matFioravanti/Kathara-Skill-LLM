"""Identità e percorsi espliciti per i compiti DNS del nuovo benchmark.

Il catalogo non deduce associazioni dalle risorse legacy. I chiamanti devono
fornire le triple autorizzate dall'esperimento.
"""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
import re

from .prompts import PROMPT_TYPES

TASK_LEVELS = ("small", "medium", "large")
DNS_TREES = ("aster", "aurora", "meridian")
LAB_LEVELS = MappingProxyType({"lab_01": "small", "lab_02": "medium", "lab_03": "large"})
_ID = re.compile(r"[A-Za-z0-9_-]+\Z")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} non valido: {value!r}")
    return value


@dataclass(frozen=True, order=True)
class TaskAssignment:
    lab_id: str
    dns_tree_id: str
    task_level: str

    def __post_init__(self):
        _identifier(self.lab_id, "lab_id")
        _identifier(self.dns_tree_id, "dns_tree_id")
        if self.task_level not in TASK_LEVELS:
            raise ValueError(f"task_level non valido: {self.task_level!r}")
        if self.lab_id not in LAB_LEVELS:
            raise ValueError(f"Laboratorio non abilitato: {self.lab_id!r}")
        if self.dns_tree_id not in DNS_TREES:
            raise ValueError(f"Albero DNS non abilitato: {self.dns_tree_id!r}")
        if self.task_level != LAB_LEVELS[self.lab_id]:
            raise ValueError(f"Livello incompatibile per {self.lab_id}: atteso {LAB_LEVELS[self.lab_id]}, ricevuto {self.task_level}")


def parse_assignments(value) -> tuple[TaskAssignment, ...]:
    """Espande le assegnazioni dichiarate, senza prodotto cartesiano implicito."""
    if not isinstance(value, list) or not value:
        raise ValueError("assignments deve essere una lista non vuota")
    result = []
    seen = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"lab_id", "dns_tree_id", "task_levels"}:
            raise ValueError(f"Assegnazione non valida: {entry!r}")
        levels = entry["task_levels"]
        if not isinstance(levels, list) or not levels:
            raise ValueError("task_levels deve essere una lista non vuota")
        for level in levels:
            assignment = TaskAssignment(entry["lab_id"], entry["dns_tree_id"], level)
            if assignment in seen:
                raise ValueError(f"Assegnazione duplicata: {assignment}")
            seen.add(assignment)
            result.append(assignment)
    return tuple(result)


def prompt_path(root: Path, dns_tree_id: str, task_level: str, prompt_type: str) -> Path:
    _identifier(dns_tree_id, "dns_tree_id")
    if task_level not in TASK_LEVELS:
        raise ValueError(f"task_level non valido: {task_level!r}")
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"prompt_type non valido: {prompt_type!r}")
    return root / "prompt" / dns_tree_id / task_level / f"{prompt_type}.md"


def task_correction_path(root: Path, assignment: TaskAssignment) -> Path:
    return (root / "scenarios" / assignment.lab_id / "tasks" /
            assignment.dns_tree_id / assignment.task_level / "correction.yaml")


def historical_correction_path(root: Path, lab_id: str, dns_tree_id: str, task_level: str) -> Path:
    """Resolve a recorded historical identity without reclassifying it under current rules."""
    _identifier(lab_id, "lab_id")
    _identifier(dns_tree_id, "dns_tree_id")
    if task_level not in TASK_LEVELS:
        raise ValueError(f"task_level non valido: {task_level!r}")
    return root / "scenarios" / lab_id / "tasks" / dns_tree_id / task_level / "correction.yaml"


def discover_dns_trees(root: Path) -> dict[str, tuple[str, ...]]:
    """Elenca alberi e livelli effettivamente presenti, senza crearne di vuoti."""
    directory = root / "prompt"
    if not directory.is_dir():
        return {}
    trees = {}
    for tree in sorted(directory.iterdir()):
        if not tree.is_dir() or tree.is_symlink() or not _ID.fullmatch(tree.name):
            continue
        levels = tuple(level for level in TASK_LEVELS
                       if (tree / level).is_dir() and not (tree / level).is_symlink())
        if levels:
            trees[tree.name] = levels
    return trees
