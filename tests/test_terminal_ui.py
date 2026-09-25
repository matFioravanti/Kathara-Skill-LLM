import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from benchmark_core.terminal_ui import pipeline_state, result, result_table


class TerminalUiTest(unittest.TestCase):
    def test_status_rendering_is_presentational_and_has_no_ansi_or_tty_dependency(self):
        state = "AUT_COMPLETED"
        output = io.StringIO()
        with redirect_stdout(output):
            pipeline_state(state)
        self.assertEqual(state, "AUT_COMPLETED")
        self.assertIn("AUT completed", output.getvalue())
        self.assertNotIn("\x1b[", output.getvalue())

    def test_completed_result_shows_available_metrics_and_skips_missing_values(self):
        metrics = {
            "scenario": "Lab_1_No_DNS", "prompt_type": "T1", "skill_mode": "dns_only",
            "run_number": 1, "status": "COMPLETED",
            "task_success": True,
            "checker": {"passed": 404, "total": 404, "pass_rate": 1.0},
            "tokens": {"input": 8412, "output": 2106},
            "timing": {"total_seconds": 48.3},
        }
        output = io.StringIO()
        with redirect_stdout(output):
            result(metrics)
        rendered = output.getvalue()
        for expected in ("404 / 404", "100.00%", "8,412", "2,106", "48.3 s", "completed"):
            self.assertIn(expected, rendered)
        self.assertIn("Task success", rendered)
        self.assertIn("PASS", rendered)

    def test_failed_run_shows_error_and_log_details(self):
        output = io.StringIO()
        with redirect_stdout(output):
            pipeline_state("CHECKER_FAILED", error="checker exited with code 1",
                           details_path="logs/checker_stderr.log")
        rendered = output.getvalue()
        self.assertIn("Checker failed", rendered)
        self.assertIn("checker exited with code 1", rendered)
        self.assertIn("logs/checker_stderr.log", rendered)

    def test_multi_run_summary_has_semantic_columns_and_rows(self):
        rows = [{"metrics": {"scenario": "Lab_1_No_DNS", "prompt_type": "T1",
                             "skill_mode": mode, "run_number": index, "status": "COMPLETED",
                             "checker": {"passed": 4, "total": 5, "pass_rate": 0.8},
                             "timing": {"total_seconds": 2.5}}}
                for index, mode in enumerate(("no_skill", "creation_only"), start=1)]
        output = io.StringIO()
        with redirect_stdout(output):
            result_table(rows, multiple_scenarios=True)
        rendered = output.getvalue()
        for expected in ("Scenario", "Prompt", "Skill mode", "Repetition", "Result",
                         "Checks", "Pass rate", "Duration", "no_skill", "creation_only"):
            self.assertIn(expected, rendered)

    def test_cli_exit_code_still_reflects_pipeline_failure(self):
        from benchmark_core.config import Config
        from benchmark_core.scenario_loader import Scenario
        from scripts import run_benchmark

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_dir = root / "scenarios/example"
            scenario_dir.mkdir(parents=True)
            scenario = Scenario("example", scenario_dir)
            prompt_file = root / "prompt/example/T1.md"
            prompt_file.parent.mkdir(parents=True)
            prompt_file.write_text("test prompt")
            config = Config(root, {"aut": {"agent": "antigravity"},
                                   "benchmark": {"repetitions": 1, "continue_on_error": True},
                                   "results": {"directory": "results"}})
            run = root / "runs/example/T1/no_skill/r001"
            (run / "evaluation").mkdir(parents=True)
            (run / "manifest.json").write_text(json.dumps({"pipeline_state": "CHECKER_FAILED"}))
            (run / "evaluation/metrics.json").write_text(json.dumps({
                "scenario": "example", "prompt_type": "T1", "skill_mode": "no_skill",
                "run_number": 1, "status": "CHECKER_FAILED", "checker": {}, "tokens": {}, "timing": {},
            }))
            output = io.StringIO()
            with patch("sys.argv", ["run_benchmark.py", "--scenario", "example", "--prompt-type", "T1"]), \
                 patch.object(run_benchmark, "load_config", return_value=config), \
                 patch.object(run_benchmark, "discover_scenarios", return_value={"example": scenario}), \
                 patch.object(run_benchmark, "preflight"), \
                 patch.object(run_benchmark, "run_one", return_value=run) as run_one, \
                 patch.object(run_benchmark, "aggregate"), redirect_stdout(output):
                code = run_benchmark.main()
            self.assertEqual(code, 1)
            run_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
