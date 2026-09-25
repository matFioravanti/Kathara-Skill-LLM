from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark_core.config import Config
from benchmark_core.checker_runner import run_checker
from benchmark_core.correction_input import (
    InvalidCorrectionError,
    MissingCorrectionError,
    correction_path,
    read_correction,
)
from benchmark_core.preflight import preflight


class ManualCorrectionsTest(unittest.TestCase):
    def test_checker_command_uses_run_lab_and_explicit_correction_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "runs/example_dns_001/T1/dns_only/r001"
            (run / "lab").mkdir(parents=True)
            (run / "lab/lab.conf").write_text("client[0]=h1\n")
            (run / "logs").mkdir()
            (run / "results").mkdir()
            correction = run / "evaluation/correction.yaml"
            correction.parent.mkdir()
            correction.write_text("manual")
            config = Config(root, {
                "checker": {"no_cache": True},
                "benchmark": {"timeout_seconds": 20},
            })

            class Process:
                pid = 123

                def wait(self, timeout=None):
                    return 0

            observed_labs = []

            def spawn_checker(command, **_kwargs):
                labs = Path(command[command.index("--labs") + 1])
                observed_labs.append((labs / "lab/lab.conf").read_text())
                return Process()

            with patch("benchmark_core.checker_runner.subprocess.Popen", side_effect=spawn_checker) as spawn, \
                 patch("benchmark_core.checker_runner.subprocess.run", return_value=type("Cleanup", (), {"returncode": 0, "stdout": "", "stderr": ""})()), \
                 patch("benchmark_core.checker_runner.parse_reports", return_value=({"task_success": True}, [])):
                result = run_checker(config, run, correction)
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index("--config") + 1], str(correction))
            self.assertEqual(observed_labs, ["client[0]=h1\n"])
            self.assertEqual(result["task_success"], True)

    def test_canonical_path_is_independent_of_mode_and_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = correction_path(root, "example_dns_001")
            canonical.parent.mkdir(parents=True)
            canonical.write_bytes(b"manual oracle\n")
            paths = {
                correction_path(root, "example_dns_001")
                for _mode in ("no_skill", "creation_only", "dns_only", "both_forced", "auto")
                for _run in range(1, 3)
            }
            self.assertEqual(paths, {canonical})
            self.assertEqual(canonical.relative_to(root).as_posix(),
                             "scenarios/example_dns_001/correction.yaml")

    def test_discovery_requires_root_correction_and_does_not_include_it_in_lab(self):
        from benchmark_core.scenario_loader import discover_scenarios
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "scenarios"
            scenario_dir = root / "example_dns_001"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("client[0]=h1\n")
            with self.assertRaisesRegex(ValueError, "correction.yaml"):
                discover_scenarios(root)
            correction = scenario_dir / "correction.yaml"
            correction.write_bytes(b"manual correction\n")
            scenario = discover_scenarios(root)["example_dns_001"]
            self.assertEqual(scenario.correction, correction.resolve())
            self.assertEqual([p.name for p in scenario.lab.iterdir()], ["lab.conf"])

    def test_missing_correction_fails_preflight_before_any_runtime_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Config(Path(temporary), {})
            with patch("benchmark_core.preflight.subprocess.run") as command:
                with self.assertRaisesRegex(MissingCorrectionError,
                                            "Missing correction file: scenarios/example_dns_001/correction.yaml"):
                    preflight(config, "codex", skill_mode="all", scenario_ids=["example_dns_001"])
            command.assert_not_called()

    def test_cli_all_aborts_before_first_mode_when_global_preflight_fails(self):
        from benchmark_core.scenario_loader import Scenario
        from scripts import run_benchmark

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_dir = root / "scenarios/example_dns_001"
            scenario_dir.mkdir(parents=True)
            scenario = Scenario("example_dns_001", scenario_dir)
            prompt_dir = root / "prompt/example_dns_001"
            prompt_dir.mkdir(parents=True)
            (prompt_dir / "T1.md").write_text("prompt")
            config = Config(root, {
                "aut": {"agent": "codex"},
                "benchmark": {"repetitions": 1, "continue_on_error": True},
                "results": {"directory": "results"},
            })
            error = MissingCorrectionError(
                "Missing correction file: scenarios/example_dns_001/correction.yaml\nNo model run was started."
            )
            with patch("sys.argv", ["run_benchmark.py", "--all", "--prompt-type", "T1", "--all-skill-modes"]), \
                 patch.object(run_benchmark, "load_config", return_value=config), \
                 patch.object(run_benchmark, "discover_scenarios", return_value={scenario.scenario_id: scenario}), \
                 patch.object(run_benchmark, "preflight", side_effect=error) as check, \
                 patch.object(run_benchmark, "run_one") as run_one:
                with self.assertRaises(MissingCorrectionError):
                    run_benchmark.main()
            check.assert_called_once()
            self.assertEqual(check.call_args.kwargs["scenario_ids"], ["example_dns_001"])
            run_one.assert_not_called()

    def test_invalid_yaml_fails_before_any_runtime_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = correction_path(root, "example_dns_001")
            path.parent.mkdir(parents=True)
            path.write_text("test: [unterminated\n", encoding="utf-8")
            with patch("benchmark_core.preflight.subprocess.run") as command:
                with self.assertRaisesRegex(InvalidCorrectionError, "Invalid correction file"):
                    preflight(Config(root, {}), "codex", skill_mode="all", scenario_ids=["example_dns_001"])
            command.assert_not_called()

    def test_read_correction_preserves_exact_bytes_and_distinguishes_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scenarios/example_dns_001/correction.yaml"
            with self.assertRaises(MissingCorrectionError):
                read_correction(path)
            path.parent.mkdir(parents=True)
            original = b"test:\n  sample: value\n"
            path.write_bytes(original)
            # A mapping is parsed before the checker-specific schema loader is called.
            with patch("kathara_lab_checker.__main__.load_config_and_lab", return_value=(None, "/tmp/unused")), \
                 patch("Kathara.parser.netkit.LabParser.LabParser.parse",
                       return_value=type("Lab", (), {"machines": [object()]})()):
                content, _digest = read_correction(path)
            self.assertEqual(content, original)
            self.assertEqual(path.read_bytes(), original)

    def test_run_pipeline_has_no_correction_generation_entrypoint(self):
        from benchmark_core import pipeline

        self.assertFalse(hasattr(pipeline, "generate_correction"))
        self.assertFalse(hasattr(pipeline, "correction_generator"))


if __name__ == "__main__":
    unittest.main()
