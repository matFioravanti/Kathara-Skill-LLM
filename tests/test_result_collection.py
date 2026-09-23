from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from benchmark_core.aggregation import aggregate
from benchmark_core.run_metrics import codex_usage, make_metrics, selected_skills
from benchmark_core.workspace import write_json


def codex_event(event_type, **fields):
    return {"type": event_type, **fields}


def command_event(command):
    return {
        "type": "item.completed",
        "item": {"id": "item_read", "type": "command_execution", "command": command},
    }


class ResultCollectionTest(unittest.TestCase):
    def test_usage_uses_only_the_last_turn_completed_and_does_not_infer_total(self):
        events = [
            codex_event("turn.completed", usage={"input_tokens": 12, "output_tokens": 3}),
            codex_event("turn.completed", usage={
                "input_tokens": 100, "cached_input_tokens": 80, "cache_write_input_tokens": 2,
                "output_tokens": 25, "reasoning_output_tokens": 7,
            }),
        ]
        self.assertEqual(codex_usage(events), {
            "input": 100, "cached_input": 80, "cache_write_input": 2,
            "output": 25, "reasoning": 7, "total": None,
        })
        self.assertIsNone(codex_usage([])["input"])

    def test_selected_skills_requires_a_traced_read_of_available_skill_md(self):
        events = [
            {"type": "item.started", "item": {"id": "failed_read", "type": "command_execution",
                                                 "command": "cat /run/lab/.codex/skills/kathara-creation/SKILL.md",
                                                 "status": "in_progress", "exit_code": None}},
            command_event("sed -n '1,200p' /run/lab/.codex/skills/kathara-dns/SKILL.md"),
            {"type": "item.completed", "item": {"id": "failed_read", "type": "command_execution",
                                                    "command": "cat /run/lab/.codex/skills/kathara-creation/SKILL.md",
                                                    "status": "completed", "exit_code": 1}},
            command_event("rg --files /run/lab/.codex/skills/kathara-creation"),
            command_event("cat /run/lab/lab.conf"),
        ]
        self.assertEqual(
            selected_skills(events, ["kathara-creation", "kathara-dns"]),
            ["kathara-dns"],
        )
        self.assertEqual(selected_skills(events[3:], ["kathara-creation", "kathara-dns"]), [])
        self.assertEqual(selected_skills(events, []), [])

    def test_metrics_keeps_available_forced_and_selected_separate_and_times_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            logs = run / "logs/aut"
            logs.mkdir(parents=True)
            (logs / "events.jsonl").write_text(
                json.dumps(codex_event(
                    "turn.completed",
                    usage={"input_tokens": 30, "cached_input_tokens": 20, "output_tokens": 8},
                )) + "\n"
                + json.dumps(command_event(
                    "sed -n '1,10p' /run/lab/.codex/skills/kathara-dns/SKILL.md"
                )) + "\n"
            )
            write_json(logs / "result.json", {"duration_seconds": 4.25, "returncode": 0})
            metadata = {
                "scenario_id": "example_dns_001", "skill_mode": "auto", "run_number": 1,
                "run_id": "example_dns_001__auto__r001", "agent": "codex", "model": "codex-local",
                "reasoning_effort": "low", "available_skills": ["kathara-creation", "kathara-dns"],
                "forced_skills": [], "aut_execution_success": True, "pipeline_state": "COMPLETED",
                "correction_sha256": "abc",
            }
            metrics = make_metrics(
                run, metadata, total_seconds=10.5, checker_seconds=3.0,
                checker_outcome={"checks_passed": 4, "checks_failed": 1,
                                 "checks_total": 5, "check_pass_rate": 0.8},
            )
            self.assertEqual(metrics["available_skills"], ["kathara-creation", "kathara-dns"])
            self.assertEqual(metrics["forced_skills"], [])
            self.assertEqual(metrics["selected_skills"], ["kathara-dns"])
            self.assertEqual(metrics["timing"], {
                "agent_seconds": 4.25, "checker_seconds": 3.0, "total_seconds": 10.5,
            })
            self.assertEqual(metrics["tokens"]["input"], 30)
            self.assertIsNone(metrics["tokens"]["total"])
            self.assertEqual(metrics["checker"]["pass_rate"], 0.8)

    def test_auto_with_valid_trace_and_no_skill_read_records_empty_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            logs = run / "logs/aut"
            logs.mkdir(parents=True)
            (logs / "events.jsonl").write_text(
                json.dumps(codex_event("turn.started")) + "\n"
                + json.dumps(command_event("cat /run/lab/lab.conf")) + "\n"
            )
            metrics = make_metrics(run, {
                "scenario_id": "example_dns_001", "skill_mode": "auto", "run_number": 1,
                "run_id": "r001", "agent": "codex", "available_skills": ["kathara-dns"],
                "forced_skills": [], "pipeline_state": "COMPLETED", "aut_execution_success": True,
            }, total_seconds=1, checker_seconds=None, checker_outcome=None)
            self.assertTrue(metrics["skill_trace_available"])
            self.assertEqual(metrics["selected_skills"], [])
            self.assertIsNone(metrics["tokens"]["input"])

    def _write_metrics_run(self, root: Path, run_number: int, *, status: str,
                           selected: list[str] | None, pass_rate: float | None,
                           input_tokens: int | None, output_tokens: int | None):
        run = root / f"example_dns_001/auto/r{run_number:03d}"
        evaluation = run / "evaluation"
        evaluation.mkdir(parents=True)
        logs = run / "logs/aut"
        logs.mkdir(parents=True)
        metrics = {
            "scenario": "example_dns_001", "skill_mode": "auto", "run_number": run_number,
            "run_id": f"example_dns_001__auto__r{run_number:03d}", "agent": "codex",
            "model": "codex-local", "reasoning_effort": "low",
            "available_skills": ["kathara-creation", "kathara-dns"], "forced_skills": [],
            "selected_skills": selected, "skill_trace_available": True,
            "agent_success": status != "AUT_FAILED", "status": status,
            "timing": {"agent_seconds": float(run_number), "checker_seconds": 2.0,
                       "total_seconds": float(run_number + 2)},
            "tokens": {"input": input_tokens, "cached_input": None, "output": output_tokens,
                       "reasoning": None, "total": None, "cache_write_input": None},
            "checker": {"passed": 1 if pass_rate is not None else None,
                        "failed": 0 if pass_rate is not None else None,
                        "total": 1 if pass_rate is not None else None, "pass_rate": pass_rate},
            "correction_sha256": "oracle-sha",
        }
        write_json(evaluation / "metrics.json", metrics)
        if pass_rate is not None:
            report = run / "results/lab/lab_result_all.csv"
            report.parent.mkdir(parents=True)
            passed = pass_rate == 1.0
            report.write_text(
                "Test Description,Passed,Reason\n"
                f"sample-{run_number},{passed},{'OK' if passed else 'failure'}\n",
                encoding="utf-8",
            )
        return run

    def test_aggregation_creates_three_csvs_with_expected_rows_summary_and_failed_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            self._write_metrics_run(runs, 1, status="COMPLETED", selected=["kathara-dns"],
                                    pass_rate=1.0, input_tokens=100, output_tokens=20)
            self._write_metrics_run(runs, 2, status="COMPLETED", selected=[],
                                    pass_rate=0.5, input_tokens=None, output_tokens=None)
            self._write_metrics_run(runs, 3, status="AUT_FAILED", selected=[],
                                    pass_rate=None, input_tokens=None, output_tokens=None)
            output = root / "results"
            with patch("benchmark_core.checker_runner.subprocess.Popen") as checker:
                run_frame, checks_frame, summary_frame = aggregate(runs, output)
            checker.assert_not_called()
            self.assertEqual(len(run_frame), 3)
            self.assertEqual(len(checks_frame), 2)
            self.assertEqual(list(checks_frame.columns), [
                "scenario", "skill_mode", "run_number", "run_id", "test_description", "passed", "reason",
            ])
            self.assertEqual(run_frame.loc[0, "available_skills"],
                             "kathara-creation;kathara-dns")
            self.assertEqual(run_frame.loc[0, "forced_skills"], "")
            self.assertEqual(run_frame.loc[0, "selected_skills"], "kathara-dns")
            self.assertEqual(run_frame.loc[2, "status"], "AUT_FAILED")
            self.assertTrue(pd.isna(run_frame.loc[2, "input_tokens"]))
            self.assertEqual(summary_frame.iloc[0]["runs"], 3)
            self.assertEqual(summary_frame.iloc[0]["successful_runs"], 2)
            self.assertEqual(summary_frame.iloc[0]["failed_runs"], 1)
            self.assertEqual(summary_frame.iloc[0]["mean_pass_rate"], 0.75)
            self.assertAlmostEqual(summary_frame.iloc[0]["skill_selection_rate"], 0.5)
            self.assertEqual({path.name for path in output.glob("*.csv")},
                             {"runs.csv", "checks.csv", "summary.csv"})

    def test_aggregation_is_idempotent_for_metrics_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            self._write_metrics_run(runs, 1, status="AUT_FAILED", selected=[],
                                    pass_rate=None, input_tokens=15, output_tokens=6)
            output = root / "results"
            output.mkdir()
            unrelated = output / "user_notes.csv"
            unrelated.write_text("preserve this user file\n", encoding="utf-8")
            with patch("benchmark_core.checker_runner.subprocess.Popen") as checker:
                first = aggregate(runs, output)
                first_bytes = {path.name: path.read_bytes() for path in output.glob("*.csv")}
                second = aggregate(runs, output)
            checker.assert_not_called()
            second_bytes = {path.name: path.read_bytes() for path in output.glob("*.csv")}
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(first[0].iloc[0]["status"], "AUT_FAILED")
            self.assertEqual(second[0].iloc[0]["input_tokens"], 15)
            self.assertEqual(second[0].iloc[0]["selected_skills"], "")
            self.assertTrue(pd.isna(second[0].iloc[0]["total_tokens"]))
            self.assertEqual(second[2].iloc[0]["failed_runs"], 1)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve this user file\n")

    def test_empty_new_layout_writes_only_header_only_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            runs.mkdir()
            (root / "corrections").mkdir()
            output = root / "results"
            run_frame, checks_frame, summary_frame = aggregate(runs, output)
            self.assertTrue(run_frame.empty)
            self.assertTrue(checks_frame.empty)
            self.assertTrue(summary_frame.empty)
            self.assertEqual(set(path.name for path in output.iterdir()),
                             {"runs.csv", "checks.csv", "summary.csv"})
            self.assertEqual(list(pd.read_csv(output / "runs.csv").columns), run_frame.columns.tolist())


if __name__ == "__main__":
    unittest.main()
