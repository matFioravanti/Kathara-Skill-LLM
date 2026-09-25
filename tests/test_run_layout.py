from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark_core.config import Config
from benchmark_core.scenario_loader import Scenario
from benchmark_core.skill_modes import execute_skill_modes
from benchmark_core.workspace import allocate_run_directory, create_workspace, logical_run_id


class RunLayoutTest(unittest.TestCase):
    def test_all_is_not_accepted_as_a_single_run_mode(self):
        from benchmark_core.pipeline import run_one

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_dir = root / "scenarios/example_dns_001"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("client[0]=h1\n")
            (root / "prompt/example_dns_001").mkdir(parents=True, exist_ok=True)
            (root / "prompt/example_dns_001/T1.md").write_text("Configure DNS")
            with self.assertRaisesRegex(ValueError, "Modalità Skill non valida"):
                run_one(None, Scenario("example_dns_001", scenario_dir), "codex", "T1", "all")
            self.assertFalse((root / "runs/example_dns_001/T1/all").exists())

    def test_numbering_is_independent_per_scenario_and_mode_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"
            first, n1 = allocate_run_directory(runs, "scenario_a", "T1", "dns_only")
            first_marker = first / "keep.txt"
            first_marker.write_text("preserve")
            second, n2 = allocate_run_directory(runs, "scenario_a", "T1", "dns_only")
            other_mode, n3 = allocate_run_directory(runs, "scenario_a", "T1", "auto")
            other_scenario, n4 = allocate_run_directory(runs, "scenario_b", "T1", "dns_only")

            self.assertEqual((n1, n2, n3, n4), (1, 2, 1, 1))
            self.assertEqual(first.relative_to(runs).as_posix(), "scenario_a/T1/dns_only/r001")
            self.assertEqual(second.relative_to(runs).as_posix(), "scenario_a/T1/dns_only/r002")
            self.assertEqual(other_mode.relative_to(runs).as_posix(), "scenario_a/T1/auto/r001")
            self.assertEqual(other_scenario.relative_to(runs).as_posix(), "scenario_b/T1/dns_only/r001")
            self.assertEqual(first_marker.read_text(), "preserve")

    def test_all_creates_five_separate_effective_mode_paths_in_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "scenarios/example_dns_001"
            (source / "lab").mkdir(parents=True)
            (source / "lab/lab.conf").write_text("client[0]=h1\n")
            (root / "prompt/example_dns_001").mkdir(parents=True, exist_ok=True)
            (root / "prompt/example_dns_001/T1.md").write_text("Configure DNS")
            scenario = Scenario("example_dns_001", source)
            created = []

            def run(mode, index, total):
                self.assertEqual(len(created), index - 1, "orchestrazione non sequenziale")
                path = create_workspace(root / "runs", scenario, "T1", mode, "Configure DNS")
                created.append((mode, path))
                return path

            list(execute_skill_modes("all", run))
            expected = ["no_skill", "creation_only", "dns_only", "both_forced", "auto"]
            self.assertEqual([mode for mode, _ in created], expected)
            self.assertEqual(
                [path.relative_to(root / "runs").as_posix() for _, path in created],
                [f"example_dns_001/T1/{mode}/r001" for mode in expected],
            )
            self.assertFalse((root / "runs/example_dns_001/all").exists())
            self.assertEqual(len({path for _, path in created}), 5)

    def test_pipeline_manifest_keeps_effective_mode_and_logical_run_id(self):
        from benchmark_core import pipeline

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_dir = root / "scenarios/example_dns_001"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("client[0]=h1\n")
            (root / "prompt/example_dns_001").mkdir(parents=True, exist_ok=True)
            (root / "prompt/example_dns_001/T1.md").write_text("Configure DNS")
            scenario = Scenario("example_dns_001", scenario_dir)
            for rel in ("skills/dns/SKILL.md", "scenarios/example_dns_001/correction.yaml"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("canonical correction")
            config = Config(root, {
                "aut": {"version": "test", "model": "codex-default", "reasoning_effort": "medium",
                        "dns_skill": "skills/dns/SKILL.md"},
                "sandbox": {"image": "fixture"}, "benchmark": {"timeout_seconds": 10},
            })
            modes = ["no_skill", "creation_only", "dns_only", "both_forced", "auto"]
            runs = []
            with patch.object(pipeline, "component_versions", return_value={}), \
                 patch.object(pipeline, "run_aut"), \
                 patch.object(pipeline, "read_correction", return_value=(b"canonical correction", "sha")), \
                 patch.object(pipeline, "validate_correction", return_value="sha"), \
                 patch.object(pipeline, "run_checker", return_value={"task_success": True}) as checker:
                for mode in modes:
                    runs.append(pipeline.run_one(config, scenario, "codex", "T1", mode))

            import json
            self.assertEqual([call.args[2] for call in checker.call_args_list],
                             [run / "evaluation/correction.yaml" for run in runs])
            self.assertTrue(all((run / "evaluation/correction.yaml").read_bytes() == b"canonical correction"
                                for run in runs))
            self.assertEqual((root / "scenarios/example_dns_001/correction.yaml").read_text(),
                             "canonical correction")
            run = runs[2]
            manifest = json.loads((run / "manifest.json").read_text())
            metrics = json.loads((run / "evaluation/metrics.json").read_text())
            self.assertEqual(manifest["run_id"], "example_dns_001__T1__dns_only__r001")
            self.assertEqual(manifest["skill_mode"], "dns_only")
            self.assertEqual(manifest["prompt_type"], "T1")
            self.assertEqual(metrics["prompt_type"], "T1")
            self.assertEqual(manifest["prompt_sha256"], __import__("hashlib").sha256(b"Configure DNS").hexdigest())
            self.assertEqual(manifest["run_directory"], "example_dns_001/T1/dns_only/r001")
            self.assertEqual(manifest["run_number"], 1)
            self.assertNotIn("all", manifest["run_id"])
            self.assertEqual(manifest["correction_source"], "scenarios/example_dns_001/correction.yaml")
            self.assertEqual(manifest["correction_snapshot"], "evaluation/correction.yaml")
            self.assertEqual((run / "evaluation/correction.yaml").read_bytes(), b"canonical correction")
            self.assertFalse((run / "lab/correction.yaml").exists())
            self.assertFalse((run / "input/lab/correction.yaml").exists())
            self.assertEqual([call.args[2] for call in checker.call_args_list],
                             [run / "evaluation/correction.yaml" for run in runs])
            self.assertNotIn("CORRECTION_GENERATION", str(manifest["state_history"]))
            self.assertEqual(manifest["artifacts"]["inspect_eval_log"],
                             "logs/aut/example_dns_001__T1__dns_only__r001.eval")
            self.assertEqual(metrics["run_id"], manifest["run_id"])
            self.assertEqual(metrics["correction_sha256"], "sha")


if __name__ == "__main__":
    unittest.main()
