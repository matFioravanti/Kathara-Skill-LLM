"""Parsing, validazione e analisi delle run per gli experiment multi-scenario."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

from .prompts import PROMPT_TYPES
from .task_catalog import TaskAssignment, parse_assignments
from .skill_modes import SKILL_MODE_CHOICES


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExperimentSpec:
    """Configurazione immutabile letta da experiment.yaml."""

    experiment_id: str
    scenarios: tuple[str, ...]
    prompt_types: tuple[str, ...]
    skill_modes: tuple[str, ...]
    repetitions: int
    source_path: Path
    assignments: tuple[TaskAssignment, ...] = ()


@dataclass(frozen=True)
class RunCell:
    """Un'unica combinazione (scenario, prompt, skill_mode, replicate)."""

    experiment_id: str
    scenario_id: str
    prompt_type: str
    skill_mode: str
    replicate: int
    assignment: TaskAssignment | None = None

    @property
    def lab_id(self):
        return self.assignment.lab_id if self.assignment else self.scenario_id

    @property
    def dns_tree_id(self):
        return self.assignment.dns_tree_id if self.assignment else None

    @property
    def task_level(self):
        return self.assignment.task_level if self.assignment else None


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------

def load_experiment(path: Path) -> ExperimentSpec:
    """Legge e valida un file experiment.yaml; fallisce con ValueError se invalido."""
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"File experiment non trovato: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Errore YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Il file experiment deve essere un mapping YAML: {path}")

    experiment_block = data.get("experiment")
    if not isinstance(experiment_block, dict):
        raise ValueError("Sezione 'experiment' mancante o non valida.")
    experiment_id = experiment_block.get("id")
    if not experiment_id or not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment.id mancante o vuoto.")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", experiment_id):
        raise ValueError(
            f"experiment.id non valido: {experiment_id!r}. "
            "Usare solo lettere, cifre, trattini e underscore."
        )

    assignments = parse_assignments(data["assignments"]) if "assignments" in data else ()
    scenarios = data.get("scenarios", [])
    if assignments and scenarios:
        raise ValueError("Usare assignments o scenarios, non entrambi")
    if not assignments:
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("'assignments' deve essere una lista non vuota")
        if any(not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", s) for s in scenarios):
            raise ValueError("ID scenario non valido")
    else:
        scenarios = list(dict.fromkeys(a.lab_id for a in assignments))

    prompt_types = data.get("prompt_types")
    if not isinstance(prompt_types, list) or not prompt_types:
        raise ValueError("'prompt_types' deve essere una lista non vuota.")
    for pt in prompt_types:
        if pt not in PROMPT_TYPES:
            raise ValueError(
                f"prompt_type non valido: {pt!r}; valori ammessi: {', '.join(PROMPT_TYPES)}"
            )

    if len(set(prompt_types)) != len(prompt_types):
        raise ValueError("prompt_types duplicati")

    skill_modes = data.get("skill_modes")
    if not isinstance(skill_modes, list) or not skill_modes:
        raise ValueError("'skill_modes' deve essere una lista non vuota.")
    for sm in skill_modes:
        if sm not in SKILL_MODE_CHOICES:
            raise ValueError(
                f"skill_mode non valido: {sm!r}; valori ammessi: {', '.join(SKILL_MODE_CHOICES)}"
            )

    if len(set(skill_modes)) != len(skill_modes):
        raise ValueError("skill_modes duplicati")

    repetitions = data.get("repetitions")
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
        raise ValueError("'repetitions' deve essere un intero >= 1.")

    return ExperimentSpec(
        experiment_id=experiment_id.strip(),
        scenarios=tuple(s.strip() for s in scenarios),
        prompt_types=tuple(prompt_types),
        skill_modes=tuple(skill_modes),
        repetitions=repetitions,
        source_path=path,
        assignments=assignments,
    )


# ---------------------------------------------------------------------------
# Matrice delle run attese
# ---------------------------------------------------------------------------

def build_run_matrix(spec: ExperimentSpec) -> list[RunCell]:
    """Genera tutte le combinazioni nell'ordine deterministico."""
    cells = []
    for assignment in (spec.assignments or tuple(None for _ in spec.scenarios)):
        scenario_id = assignment.lab_id if assignment else spec.scenarios[len(cells) // (len(spec.prompt_types) * len(spec.skill_modes) * spec.repetitions)]
        for prompt_type in spec.prompt_types:
            for skill_mode in spec.skill_modes:
                for replicate in range(1, spec.repetitions + 1):
                    cells.append(RunCell(
                        experiment_id=spec.experiment_id,
                        scenario_id=scenario_id,
                        prompt_type=prompt_type,
                        skill_mode=skill_mode,
                        replicate=replicate,
                        assignment=assignment,
                    ))
    return cells


# ---------------------------------------------------------------------------
# Stato delle run esistenti
# ---------------------------------------------------------------------------

_INFRA_FAILURE_STATES = frozenset({
    "AUT_FAILED", "CHECKER_FAILED", "CORRECTION_MISSING", "CORRECTION_INVALID",
    "PENDING",
})
_COMPLETED_STATE = "COMPLETED"


def _is_valid_run_dir(path: Path) -> bool:
    return path.is_dir() and bool(re.fullmatch(r"r\d{3,}", path.name))


def _read_manifest(run: Path) -> dict | None:
    manifest_path = run / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_replicate(manifest: dict) -> int | None:
    """Restituisce replicate se presente, altrimenti None."""
    return manifest.get("replicate") if isinstance(manifest.get("replicate"), int) else None


@dataclass
class RunStatus:
    """Classifica una singola run già presente su disco."""

    run: Path
    run_number: int
    replicate: int | None
    pipeline_state: str | None
    experiment_id: str | None

    @property
    def is_completed(self) -> bool:
        return self.pipeline_state == _COMPLETED_STATE

    @property
    def is_infrastructure_failure(self) -> bool:
        return self.pipeline_state in _INFRA_FAILURE_STATES and self.pipeline_state != _COMPLETED_STATE

    @property
    def is_valid_observation(self) -> bool:
        """COMPLETED con o senza task_success è un'osservazione valida."""
        return self.pipeline_state == _COMPLETED_STATE


@dataclass
class CellAnalysis:
    """Analisi di tutte le run fisiche per una cella (scenario, prompt, skill_mode)."""

    cell_base: tuple[str, str, str]   # (scenario_id, prompt_type, skill_mode)
    experiment_id: str
    all_runs: list[RunStatus] = field(default_factory=list)

    def completed_replicates(self) -> set[int]:
        return {r.replicate for r in self.all_runs
                if r.is_valid_observation and r.replicate is not None}

    def infra_failed_run_numbers(self) -> list[int]:
        return [r.run_number for r in self.all_runs if r.is_infrastructure_failure]


def analyse_existing_runs(
    runs_root: Path,
    spec: ExperimentSpec,
) -> dict[tuple[str, str, str], CellAnalysis]:
    """
    Legge i manifest esistenti in runs/ e classifica ogni run per la cella corrispondente.
    Restituisce un dict keyed per (scenario_id, prompt_type, skill_mode).
    """
    analyses = {}
    for cell in build_run_matrix(spec):
        key = (cell.lab_id, cell.dns_tree_id, cell.task_level, cell.prompt_type, cell.skill_mode) if cell.assignment else (cell.scenario_id, cell.prompt_type, cell.skill_mode)
        if key in analyses:
            continue
        analysis = CellAnalysis(cell_base=key, experiment_id=spec.experiment_id)
        mode_root = (runs_root / spec.experiment_id / cell.lab_id / cell.dns_tree_id / cell.task_level / cell.prompt_type / cell.skill_mode) if cell.assignment else (runs_root / cell.scenario_id / cell.prompt_type / cell.skill_mode)
        if mode_root.is_dir():
            for run_dir in sorted(mode_root.iterdir(), key=lambda p: p.name):
                if not _is_valid_run_dir(run_dir):
                    continue
                manifest = _read_manifest(run_dir)
                if manifest is None:
                    continue
                run_exp_id = manifest.get("experiment_id")
                if cell.assignment:
                    if (run_exp_id, manifest.get("lab_id"), manifest.get("dns_tree_id"), manifest.get("task_level"), manifest.get("prompt_type"), manifest.get("skill_mode")) != (spec.experiment_id, cell.lab_id, cell.dns_tree_id, cell.task_level, cell.prompt_type, cell.skill_mode):
                        continue
                elif run_exp_id is not None and run_exp_id != spec.experiment_id:
                    continue
                analysis.all_runs.append(RunStatus(run_dir, int(run_dir.name[1:]), _run_replicate(manifest), manifest.get("pipeline_state"), run_exp_id))
        analyses[key] = analysis
    return analyses


# ---------------------------------------------------------------------------
# Logica resume
# ---------------------------------------------------------------------------

@dataclass
class ResumeDecision:
    """Risultato dell'analisi per una singola cella × replicate."""

    cell: RunCell
    should_run: bool
    reason: str   # "missing" | "completed" | "infra_failed_reassigned"


def compute_resume_plan(
    spec: ExperimentSpec,
    analyses: dict[tuple[str, str, str], CellAnalysis],
) -> list[ResumeDecision]:
    """
    Determina quali combinazioni eseguire basandosi sulle run esistenti.

    Algoritmo:
    - Per ogni cella (scenario, prompt, skill_mode, replicate):
      * Se replicate è già presente tra le run COMPLETED di quell'experiment → skip
      * Altrimenti → eseguire
    """
    decisions = []
    cells = build_run_matrix(spec)
    for cell in cells:
        key = (cell.lab_id, cell.dns_tree_id, cell.task_level, cell.prompt_type, cell.skill_mode) if cell.assignment else (cell.scenario_id, cell.prompt_type, cell.skill_mode)
        analysis = analyses.get(key)
        if analysis is None:
            decisions.append(ResumeDecision(cell=cell, should_run=True, reason="missing"))
            continue
        completed = analysis.completed_replicates()
        if cell.replicate in completed:
            decisions.append(ResumeDecision(cell=cell, should_run=False, reason="completed"))
        else:
            decisions.append(ResumeDecision(cell=cell, should_run=True, reason="missing"))
    return decisions


# ---------------------------------------------------------------------------
# Statistiche di riepilogo
# ---------------------------------------------------------------------------

@dataclass
class ExperimentSummary:
    expected: int
    completed: int
    infra_failed: int
    missing: int

    @property
    def table_lines(self) -> list[str]:
        return [
            f"  Expected observations:  {self.expected:>5}",
            f"  Completed:              {self.completed:>5}",
            f"  Infrastructure failed:  {self.infra_failed:>5}",
            f"  Missing:                {self.missing:>5}",
        ]


def compute_summary(
    spec: ExperimentSpec,
    analyses: dict[tuple[str, str, str], CellAnalysis],
) -> ExperimentSummary:
    decisions = compute_resume_plan(spec, analyses)
    completed = sum(1 for d in decisions if not d.should_run)
    missing = sum(1 for d in decisions if d.should_run)
    infra_count = 0
    for analysis in analyses.values():
        infra_count += len(analysis.infra_failed_run_numbers())
    return ExperimentSummary(
        expected=len(decisions),
        completed=completed,
        infra_failed=infra_count,
        missing=missing,
    )


# ---------------------------------------------------------------------------
# Validazione prerequisiti esperimento
# ---------------------------------------------------------------------------

def validate_experiment_prerequisites(
    spec: ExperimentSpec,
    config,
    scenarios_dict: dict,
) -> None:
    """
    Verifica staticamente che tutti i requisiti dell'esperimento siano soddisfatti
    PRIMA di fare qualsiasi chiamata al modello.
    Lancia ValueError se c'è un problema.
    """
    from .correction_input import correction_path, validate_correction, validate_correction_lab
    from .prompts import resolve_prompt, render_task_prompt

    missing_scenarios = [s for s in spec.scenarios if s not in scenarios_dict]
    if missing_scenarios:
        raise ValueError(
            f"Scenari non trovati: {', '.join(missing_scenarios)}. "
            f"Disponibili: {', '.join(sorted(scenarios_dict))}"
        )

    for assignment in spec.assignments:
        for prompt_type in spec.prompt_types:
            render_task_prompt(config.root, assignment, prompt_type)
        validate_correction(correction_path(config.root, assignment))
        validate_correction_lab(correction_path(config.root, assignment), scenarios_dict[assignment.lab_id].lab)
    if not spec.assignments:
        for scenario_id in spec.scenarios:
            for prompt_type in spec.prompt_types:
                resolve_prompt(config.root, scenario_id, prompt_type)
            validate_correction(correction_path(config.root, scenario_id))
