"""Test per l'experiment layer: parsing, matrice, resume, workspace isolation, rerun correction."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from benchmark_core.experiment import (
    ExperimentSpec,
    RunCell,
    build_run_matrix,
    compute_resume_plan,
    compute_summary,
    analyse_existing_runs,
    load_experiment,
    validate_experiment_prerequisites,
)
from benchmark_core.workspace import write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_experiment_yaml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _make_spec(*, experiment_id="test_exp", scenarios=("Lab_01",),
               prompt_types=("T1",), skill_modes=("no_skill",), repetitions=1) -> ExperimentSpec:
    import yaml as _yaml
    import os
    data = {
        "experiment": {"id": experiment_id},
        "scenarios": list(scenarios),
        "prompt_types": list(prompt_types),
        "skill_modes": list(skill_modes),
        "repetitions": repetitions,
    }
    fd, name = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            _yaml.dump(data, f)
        return load_experiment(Path(name))
    finally:
        Path(name).unlink(missing_ok=True)


def _write_run(runs_root: Path, scenario: str, prompt: str, mode: str,
               run_number: int, pipeline_state: str,
               experiment_id: str | None = None, replicate: int | None = None) -> Path:
    run = runs_root / scenario / prompt / mode / f"r{run_number:03d}"
    (run / "evaluation").mkdir(parents=True, exist_ok=True)
    (run / "lab").mkdir(parents=True, exist_ok=True)
    (run / "input/lab").mkdir(parents=True, exist_ok=True)
    (run / "logs/aut").mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": f"{scenario}__{prompt}__{mode}__r{run_number:03d}",
        "run_number": run_number,
        "scenario_id": scenario, "prompt_type": prompt, "skill_mode": mode,
        "pipeline_state": pipeline_state,
        "experiment_id": experiment_id,
        "replicate": replicate if replicate is not None else run_number,
        "aut_execution_success": pipeline_state not in ("AUT_FAILED", "PENDING"),
        "task_success": (pipeline_state == "COMPLETED"),
        "checker_execution_success": pipeline_state == "COMPLETED" or None,
        "evaluation_revision": 0,
    }
    write_json(run / "manifest.json", manifest)
    metrics = {
        "scenario": scenario, "scenario_id": scenario,
        "prompt_type": prompt, "skill_mode": mode,
        "run_number": run_number, "replicate": replicate if replicate is not None else run_number,
        "experiment_id": experiment_id, "run_id": manifest["run_id"],
        "agent": "codex", "model": "test", "status": pipeline_state,
        "timing": {}, "tokens": {}, "checker": {}, "evaluation_revision": 0,
    }
    write_json(run / "evaluation/metrics.json", metrics)
    return run


# ---------------------------------------------------------------------------
# Test: Parsing experiment.yaml
# ---------------------------------------------------------------------------

class TestExperimentParsing(unittest.TestCase):

    def _parse(self, yaml_content: str) -> ExperimentSpec:
        import os
        fd, name = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(yaml_content)
            return load_experiment(Path(name))
        finally:
            Path(name).unlink(missing_ok=True)

    def test_valid_experiment_parses_correctly(self):
        spec = self._parse("""
experiment:
  id: my_exp
scenarios:
  - Lab_01
  - Lab_02
prompt_types:
  - T1
  - T3
skill_modes:
  - no_skill
  - dns_only
repetitions: 2
""")
        self.assertEqual(spec.experiment_id, "my_exp")
        self.assertEqual(spec.scenarios, ("Lab_01", "Lab_02"))
        self.assertEqual(spec.prompt_types, ("T1", "T3"))
        self.assertEqual(spec.skill_modes, ("no_skill", "dns_only"))
        self.assertEqual(spec.repetitions, 2)

    def test_missing_experiment_id_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("""
experiment:
  id: ""
scenarios: [Lab_01]
prompt_types: [T1]
skill_modes: [no_skill]
repetitions: 1
""")
        self.assertIn("id", str(ctx.exception).lower())

    def test_invalid_prompt_type_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("""
experiment:
  id: exp1
scenarios: [Lab_01]
prompt_types: [T99]
skill_modes: [no_skill]
repetitions: 1
""")
        self.assertIn("T99", str(ctx.exception))

    def test_invalid_skill_mode_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("""
experiment:
  id: exp1
scenarios: [Lab_01]
prompt_types: [T1]
skill_modes: [nonexistent_mode]
repetitions: 1
""")
        self.assertIn("nonexistent_mode", str(ctx.exception))

    def test_repetitions_zero_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("""
experiment:
  id: exp1
scenarios: [Lab_01]
prompt_types: [T1]
skill_modes: [no_skill]
repetitions: 0
""")
        self.assertIn("repetitions", str(ctx.exception).lower())

    def test_missing_experiment_block_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._parse("""
scenarios: [Lab_01]
prompt_types: [T1]
skill_modes: [no_skill]
repetitions: 1
""")
        self.assertIn("experiment", str(ctx.exception).lower())

    def test_single_combination_parses_correctly(self):
        spec = self._parse("""
experiment:
  id: single
scenarios: [Lab_01]
prompt_types: [T1]
skill_modes: [no_skill]
repetitions: 1
""")
        self.assertEqual(spec.repetitions, 1)
        self.assertEqual(len(spec.scenarios), 1)


# ---------------------------------------------------------------------------
# Test: Matrice run
# ---------------------------------------------------------------------------

class TestRunMatrix(unittest.TestCase):

    def test_matrix_product_is_correct(self):
        spec = _make_spec(
            scenarios=("S1", "S2"),
            prompt_types=("T1", "T2", "T3"),
            skill_modes=("no_skill", "dns_only"),
            repetitions=4,
        )
        matrix = build_run_matrix(spec)
        # 2 × 3 × 2 × 4 = 48
        self.assertEqual(len(matrix), 48)

    def test_single_cell_matrix(self):
        spec = _make_spec(scenarios=("Lab_01",), prompt_types=("T1",),
                          skill_modes=("no_skill",), repetitions=1)
        matrix = build_run_matrix(spec)
        self.assertEqual(len(matrix), 1)
        cell = matrix[0]
        self.assertIsInstance(cell, RunCell)
        self.assertEqual(cell.scenario_id, "Lab_01")
        self.assertEqual(cell.prompt_type, "T1")
        self.assertEqual(cell.skill_mode, "no_skill")
        self.assertEqual(cell.replicate, 1)

    def test_matrix_order_is_deterministic(self):
        spec = _make_spec(
            scenarios=("S1", "S2"),
            prompt_types=("T1", "T2"),
            skill_modes=("no_skill", "dns_only"),
            repetitions=2,
        )
        matrix1 = build_run_matrix(spec)
        matrix2 = build_run_matrix(spec)
        self.assertEqual([c.scenario_id for c in matrix1],
                         [c.scenario_id for c in matrix2])
        # Primo scenario prima
        self.assertTrue(all(c.scenario_id == "S1" for c in matrix1[:8]))
        # Ordine replicates per cella
        cell_repls = [c.replicate for c in matrix1 if c.scenario_id == "S1" and c.prompt_type == "T1" and c.skill_mode == "no_skill"]
        self.assertEqual(cell_repls, [1, 2])

    def test_750_observations(self):
        scenarios = tuple(f"Lab_{i:02d}" for i in range(1, 11))  # 10 scenari
        spec = _make_spec(
            scenarios=scenarios,
            prompt_types=("T1", "T2", "T3", "T4", "T5"),
            skill_modes=("no_skill", "creation_only", "dns_only", "both_forced", "auto"),
            repetitions=3,
        )
        self.assertEqual(len(build_run_matrix(spec)), 750)


# ---------------------------------------------------------------------------
# Test: Resume logic
# ---------------------------------------------------------------------------

class TestResumePlan(unittest.TestCase):

    def test_completed_replicate_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            spec = _make_spec(scenarios=("Lab_01",), prompt_types=("T1",),
                               skill_modes=("no_skill",), repetitions=3,
                               experiment_id="test_exp")
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "COMPLETED",
                       experiment_id="test_exp", replicate=1)
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 2, "COMPLETED",
                       experiment_id="test_exp", replicate=2)
            analyses = analyse_existing_runs(runs_root, spec)
            decisions = compute_resume_plan(spec, analyses)
            self.assertEqual(len(decisions), 3)
            skip_replicates = [d.cell.replicate for d in decisions if not d.should_run]
            run_replicates = [d.cell.replicate for d in decisions if d.should_run]
            self.assertIn(1, skip_replicates)
            self.assertIn(2, skip_replicates)
            self.assertIn(3, run_replicates)

    def test_task_success_false_is_completed_observation(self):
        """Una run COMPLETED con task_success=False è un'osservazione valida → skip da resume."""
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            spec = _make_spec(scenarios=("Lab_01",), prompt_types=("T1",),
                               skill_modes=("no_skill",), repetitions=1,
                               experiment_id="test_exp")
            run = _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "COMPLETED",
                              experiment_id="test_exp", replicate=1)
            # Sovrascriviamo task_success=False ma pipeline_state=COMPLETED
            manifest = json.loads((run / "manifest.json").read_text())
            manifest["task_success"] = False
            write_json(run / "manifest.json", manifest)
            analyses = analyse_existing_runs(runs_root, spec)
            decisions = compute_resume_plan(spec, analyses)
            self.assertEqual(len(decisions), 1)
            self.assertFalse(decisions[0].should_run)  # Deve essere saltata (osservazione valida)

    def test_infrastructure_failure_leaves_replicate_open(self):
        """Una run AUT_FAILED non occupa una replicate → la cella rimane da eseguire."""
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            spec = _make_spec(scenarios=("Lab_01",), prompt_types=("T1",),
                               skill_modes=("no_skill",), repetitions=1,
                               experiment_id="test_exp")
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "AUT_FAILED",
                       experiment_id="test_exp", replicate=1)
            analyses = analyse_existing_runs(runs_root, spec)
            decisions = compute_resume_plan(spec, analyses)
            self.assertEqual(len(decisions), 1)
            self.assertTrue(decisions[0].should_run)  # Ancora da eseguire

    def test_resume_does_not_rerun_completed(self):
        """--resume con tutte le replicate completate → nessuna run."""
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            spec = _make_spec(scenarios=("Lab_01",), prompt_types=("T1",),
                               skill_modes=("no_skill",), repetitions=2,
                               experiment_id="test_exp")
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "COMPLETED",
                       experiment_id="test_exp", replicate=1)
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 2, "COMPLETED",
                       experiment_id="test_exp", replicate=2)
            analyses = analyse_existing_runs(runs_root, spec)
            decisions = compute_resume_plan(spec, analyses)
            should_run = [d for d in decisions if d.should_run]
            self.assertEqual(len(should_run), 0)


# ---------------------------------------------------------------------------
# Test: Workspace isolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation(unittest.TestCase):

    def test_two_replicates_start_from_baseline(self):
        """Due replicate devono partire entrambe dal baseline originale, non dalla run precedente."""
        from benchmark_core.workspace import create_workspace, tree_hash
        from benchmark_core.scenario_loader import Scenario
        from benchmark_core import pipeline

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario_dir = root / "scenarios/Lab_01"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("baseline\n")
            scenario = Scenario("Lab_01", scenario_dir)
            baseline_hash = tree_hash(scenario.lab)

            # Prima run: simula modifica del lab
            run1 = create_workspace(root / "runs", scenario, "T1", "no_skill", "prompt")
            (run1 / "lab" / "extra.txt").write_text("modifica AUT\n")
            self.assertNotEqual(tree_hash(run1 / "lab"), baseline_hash)

            # Seconda run: deve partire dal baseline originale
            run2 = create_workspace(root / "runs", scenario, "T1", "no_skill", "prompt")
            self.assertEqual(tree_hash(run2 / "lab"), baseline_hash)
            self.assertEqual(tree_hash(run2 / "input/lab"), baseline_hash)

            # Il baseline originale non deve essere stato modificato
            self.assertEqual(tree_hash(scenario.lab), baseline_hash)


# ---------------------------------------------------------------------------
# Test: Rerun correction
# ---------------------------------------------------------------------------

class TestRerunCorrectionExperiment(unittest.TestCase):

    def _fixture(self, root: Path, scenario: str, prompt: str, mode: str, run_number: int,
                 experiment_id: str | None = None, replicate: int | None = None) -> tuple[Path, Path]:
        run = _write_run(root / "runs", scenario, prompt, mode, run_number, "COMPLETED",
                          experiment_id=experiment_id, replicate=replicate)
        (run / "lab/lab.conf").write_text("AUT output\n")
        (run / "input/lab/lab.conf").write_text("baseline\n")
        (run / "logs/aut/events.jsonl").write_text('{"type":"turn.completed","usage":{}}\n')
        (run / "logs/aut/result.json").write_text('{"duration_seconds": 5}\n')
        correction = root / f"scenarios/{scenario}/correction.yaml"
        correction.parent.mkdir(parents=True, exist_ok=True)
        correction.write_bytes(b"correction content\n")
        return run, correction

    def test_rerun_correction_does_not_invoke_aut(self):
        """--rerun-correction non deve eseguire nuove chiamate AUT."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, correction = self._fixture(root, "Lab_01", "T1", "no_skill", 1,
                                             experiment_id="test_exp", replicate=1)
            lab_before = (run / "lab/lab.conf").read_bytes()
            input_before = (run / "input/lab/lab.conf").read_bytes()
            aut_before = (run / "logs/aut/events.jsonl").read_bytes()

            from benchmark_core.config import Config
            from benchmark_core.pipeline import reevaluate_run
            import hashlib

            config = Config(root, {"checker": {"no_cache": True}, "benchmark": {"timeout_seconds": 10},
                                    "results": {"directory": "results"}})
            sha = hashlib.sha256(correction.read_bytes()).hexdigest()
            outcome = {"checks_passed": 2, "checks_failed": 0, "checks_total": 2,
                        "check_pass_rate": 1.0, "task_success": True}

            with patch("benchmark_core.pipeline.run_aut") as mock_aut, \
                 patch("benchmark_core.pipeline.read_correction", return_value=(correction.read_bytes(), sha)), \
                 patch("benchmark_core.pipeline.validate_correction", return_value=sha), \
                 patch("benchmark_core.pipeline.run_checker", return_value=outcome):
                reevaluate_run(config, run)

            mock_aut.assert_not_called()
            self.assertEqual((run / "lab/lab.conf").read_bytes(), lab_before)
            self.assertEqual((run / "input/lab/lab.conf").read_bytes(), input_before)
            self.assertEqual((run / "logs/aut/events.jsonl").read_bytes(), aut_before)

    def test_rerun_correction_updates_evaluation_revision(self):
        """--rerun-correction deve incrementare evaluation_revision."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, correction = self._fixture(root, "Lab_01", "T1", "no_skill", 1,
                                             experiment_id="test_exp", replicate=1)
            from benchmark_core.config import Config
            from benchmark_core.pipeline import reevaluate_run
            import hashlib

            config = Config(root, {"checker": {"no_cache": True}, "benchmark": {"timeout_seconds": 10},
                                    "results": {"directory": "results"}})
            sha = hashlib.sha256(correction.read_bytes()).hexdigest()
            outcome = {"checks_passed": 1, "checks_failed": 1, "checks_total": 2,
                        "check_pass_rate": 0.5, "task_success": False}

            with patch("benchmark_core.pipeline.read_correction", return_value=(correction.read_bytes(), sha)), \
                 patch("benchmark_core.pipeline.validate_correction", return_value=sha), \
                 patch("benchmark_core.pipeline.run_checker", return_value=outcome):
                reevaluate_run(config, run)

            manifest = json.loads((run / "manifest.json").read_text())
            self.assertEqual(manifest["evaluation_revision"], 1)
            self.assertIn("last_reevaluated_at", manifest)


# ---------------------------------------------------------------------------
# Test: Aggregation backward compatibility
# ---------------------------------------------------------------------------

class TestAggregationBackwardCompat(unittest.TestCase):

    def _write_legacy_run(self, runs_root: Path, run_number: int):
        """Run storica senza experiment_id e replicate."""
        run = runs_root / f"example_dns_001/T1/auto/r{run_number:03d}"
        (run / "evaluation").mkdir(parents=True, exist_ok=True)
        metrics = {
            "scenario": "example_dns_001", "scenario_id": "example_dns_001",
            "prompt_type": "T1", "skill_mode": "auto",
            "run_number": run_number, "run_id": f"example_dns_001__T1__auto__r{run_number:03d}",
            "agent": "codex", "model": "legacy-model", "status": "COMPLETED",
            "timing": {}, "tokens": {}, "checker": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
            # NESSUN experiment_id, NESSUN replicate
        }
        write_json(run / "evaluation/metrics.json", metrics)
        write_json(run / "manifest.json", {
            "scenario_id": "example_dns_001", "prompt_type": "T1", "skill_mode": "auto",
            "run_number": run_number, "pipeline_state": "COMPLETED",
            "task_success": True, "checker_execution_success": True,
            # Senza experiment_id e replicate
        })
        return run

    def test_legacy_runs_without_experiment_id_are_aggregable(self):
        from benchmark_core.aggregation import aggregate
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            self._write_legacy_run(runs_root, 1)
            self._write_legacy_run(runs_root, 2)
            with patch("benchmark_core.checker_runner.subprocess.Popen"):
                run_frame, _, summary = aggregate(runs_root, Path(tmp) / "results")
            self.assertEqual(len(run_frame), 2)
            # experiment_id è None per run legacy
            self.assertTrue(run_frame["experiment_id"].isna().all())
            # replicate viene backfilled con run_number
            self.assertEqual(list(run_frame["replicate"]), [1, 2])
            self.assertIn("experiment_id", summary.columns)
            self.assertIn("prompt_type", summary.columns)

    def test_experiment_id_and_replicate_in_aggregation(self):
        from benchmark_core.aggregation import aggregate
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "COMPLETED",
                       experiment_id="thesis", replicate=1)
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 2, "COMPLETED",
                       experiment_id="thesis", replicate=2)
            with patch("benchmark_core.checker_runner.subprocess.Popen"):
                run_frame, _, summary = aggregate(runs_root, Path(tmp) / "results")
            self.assertFalse(run_frame["experiment_id"].isna().any())
            self.assertEqual(list(run_frame["replicate"]), [1, 2])
            self.assertEqual(list(run_frame["experiment_id"]), ["thesis", "thesis"])
            # Summary deve avere experiment_id e prompt_type
            self.assertIn("experiment_id", summary.columns)
            self.assertIn("prompt_type", summary.columns)

    def test_summary_has_prompt_type_column(self):
        """Verifica il fix: prompt_type deve essere visibile nel Summary."""
        from benchmark_core.aggregation import SUMMARY_COLUMNS
        self.assertIn("prompt_type", SUMMARY_COLUMNS)

    def test_excel_has_additional_sheets(self):
        from benchmark_core.aggregation import aggregate
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = Path(tmp) / "runs"
            _write_run(runs_root, "Lab_01", "T1", "no_skill", 1, "COMPLETED",
                       experiment_id="test", replicate=1)
            with patch("benchmark_core.checker_runner.subprocess.Popen"):
                aggregate(runs_root, Path(tmp) / "results")
            with pd.ExcelFile(Path(tmp) / "results/benchmark.xlsx") as wb:
                self.assertIn("Runs", wb.sheet_names)
                self.assertIn("Checks", wb.sheet_names)
                self.assertIn("Summary", wb.sheet_names)
                self.assertIn("Dashboard", wb.sheet_names)
                self.assertIn("Lab Summary", wb.sheet_names)
                self.assertIn("Prompt Summary", wb.sheet_names)
                self.assertIn("Skill Summary", wb.sheet_names)
                self.assertIn("Token Analysis", wb.sheet_names)
                self.assertIn("Time Analysis", wb.sheet_names)
                self.assertIn("Failures", wb.sheet_names)


if __name__ == "__main__":
    unittest.main()
