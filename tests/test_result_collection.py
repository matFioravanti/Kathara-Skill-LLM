from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from benchmark_core.aggregation import _check_category, aggregate
from benchmark_core.run_metrics import codex_usage, make_metrics
from benchmark_core.workspace import write_json



def codex_event(event_type, **fields):
    return {"type": event_type, **fields}


def command_event(command):
    return {
        "type": "item.completed",
        "item": {"id": "item_read", "type": "command_execution", "command": command},
    }


class ResultCollectionTest(unittest.TestCase):
    def test_check_categories_cover_network_and_dns_checks(self):
        cases = {
            "Check existence of `r1`": "topology",
            "Verifying the IP address (10.1.0.1/24) assigned to eth0 of r1": "addressing",
            "Checking the routing table of r1": "routing",
            "Verifying `10.1.0.10` reachable from device `r1`": "reachability",
            "Checking on `ns.example` is the authority for domain `example`": "dns_authority",
            "Checking that named is running on device `pc2dual`": "dns_authority",
            "Checking that ospfd is not running on device `r1`": "routing",
            "Checking that `10.3.0.30` is the local name server for device `pc1`": "dns_resolution",
            "Checking correctness of DNS records": "dns_record",
            "HTTP check 'http://example.test' on client": "http",
            "Checking the output of the command 'custom'": "custom",
            "An unclassified validation": "other",
        }
        for description, expected in cases.items():
            with self.subTest(description=description):
                self.assertEqual(_check_category(description), expected)

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



    def test_metrics_keeps_available_and_forced_separate_and_times_distinct(self):
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
                "run_id": "example_dns_001__T1__auto__r001", "agent": "codex", "model": "codex-local",
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
            self.assertEqual(metrics["timing"], {
                "agent_seconds": 4.25, "checker_seconds": 3.0, "total_seconds": 10.5,
            })
            self.assertEqual(metrics["tokens"]["input"], 30)
            self.assertIsNone(metrics["tokens"]["total"])
            self.assertEqual(metrics["checker"]["pass_rate"], 0.8)



    def _write_metrics_run(self, root: Path, run_number: int, *, status: str,
                           pass_rate: float | None,
                           input_tokens: int | None, output_tokens: int | None,
                           scenario: str = "example_dns_001"):
        run = root / f"{scenario}/T1/auto/r{run_number:03d}"
        evaluation = run / "evaluation"
        evaluation.mkdir(parents=True)
        logs = run / "logs/aut"
        logs.mkdir(parents=True)
        metrics = {
            "scenario": scenario, "prompt_type": "T1", "skill_mode": "auto", "run_number": run_number,
            "run_id": f"{scenario}__T1__auto__r{run_number:03d}", "agent": "codex",
            "model": "codex-local", "reasoning_effort": "low",
            "available_skills": ["kathara-creation", "kathara-dns"], "forced_skills": [],
            "agent_success": status != "AUT_FAILED", "status": status,
            "timing": {"agent_seconds": float(run_number), "checker_seconds": 2.0,
                       "total_seconds": float(run_number + 2)},
            "tokens": {"input": input_tokens, "cached_input": None, "output": output_tokens,
                       "reasoning": None, "total": None, "cache_write_input": None},
            "checker": {"passed": 1 if pass_rate is not None else None,
                        "failed": (0 if pass_rate == 1.0 else 1) if pass_rate is not None else None,
                        "total": (1 if pass_rate == 1.0 else 2) if pass_rate is not None else None,
                        "pass_rate": pass_rate},
            "correction_sha256": "oracle-sha",
        }
        write_json(evaluation / "metrics.json", metrics)
        write_json(run / "manifest.json", {
            "scenario_id": scenario, "prompt_type": "T1", "skill_mode": "auto",
            "run_number": run_number, "run_id": metrics["run_id"], "agent": "codex",
            "model": "codex-local", "reasoning_effort": "low", "pipeline_state": status,
            "checker_execution_success": True if status == "COMPLETED" else None,
            "task_success": (pass_rate == 1.0) if status == "COMPLETED" and pass_rate is not None else None,
        })
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
            self._write_metrics_run(runs, 1, status="COMPLETED",
                                    pass_rate=1.0, input_tokens=100, output_tokens=20)
            self._write_metrics_run(runs, 2, status="COMPLETED",
                                    pass_rate=0.5, input_tokens=None, output_tokens=None)
            self._write_metrics_run(runs, 3, status="AUT_FAILED",
                                    pass_rate=None, input_tokens=None, output_tokens=None)
            output = root / "results"
            with patch("benchmark_core.checker_runner.subprocess.Popen") as checker:
                run_frame, checks_frame, summary_frame = aggregate(runs, output)
            checker.assert_not_called()
            self.assertEqual(len(run_frame), 3)
            self.assertEqual(len(checks_frame), 2)
            self.assertEqual(list(checks_frame.columns), [
                "ID", "Lab", "T", "experiment_id", "skill_mode",
                "repetition", "replicate",
                "agent", "model",
                "category", "test_description", "passed", "reason",
            ])
            self.assertEqual(checks_frame.loc[0, "category"], "other")
            self.assertEqual(run_frame.loc[2, "status"], "AUT_FAILED")
            self.assertEqual(run_frame.loc[0, "task_success"], True)
            self.assertEqual(run_frame.loc[1, "task_success"], False)
            self.assertTrue(pd.isna(run_frame.loc[2, "input_tokens"]))
            self.assertEqual(summary_frame.iloc[0]["total_runs"], 3)
            self.assertEqual(summary_frame.iloc[0]["pipeline_completed_runs"], 2)
            self.assertEqual(summary_frame.iloc[0]["evaluated_runs"], 2)
            self.assertEqual(summary_frame.iloc[0]["task_success_runs"], 1)
            self.assertEqual(summary_frame.iloc[0]["task_failed_runs"], 1)
            self.assertEqual(summary_frame.iloc[0]["task_success_rate"], 0.5)
            self.assertEqual(summary_frame.iloc[0]["mean_pass_rate"], 0.75)
            self.assertEqual({path.name for path in output.glob("*.csv")},
                             {"runs.csv", "checks.csv", "summary.csv"})
            with pd.ExcelFile(output / "benchmark.xlsx") as workbook:
                # I fogli di base sono sempre presenti
                self.assertIn("Runs", workbook.sheet_names)
                self.assertIn("Checks", workbook.sheet_names)
                self.assertIn("Summary", workbook.sheet_names)
                self.assertEqual(pd.read_excel(workbook, sheet_name="Runs").loc[0, "ID"],
                                 "example_dns_001__T1__auto__r001")
                self.assertEqual(pd.read_excel(workbook, sheet_name="Checks").shape[0], 2)
                self.assertEqual(pd.read_excel(workbook, sheet_name="Summary").loc[0, "total_runs"], 3)
                for sheet, frame in zip(("Runs", "Checks", "Summary"),
                                        (run_frame, checks_frame, summary_frame)):
                    excel_frame = pd.read_excel(workbook, sheet_name=sheet)
                    self.assertEqual(excel_frame.columns.tolist(), frame.columns.tolist())
                    self.assertEqual(len(excel_frame), len(frame))
                    for column in frame.columns:
                        for expected, actual in zip(frame[column], excel_frame[column]):
                            if pd.isna(expected):
                                self.assertTrue(pd.isna(actual))
                            elif isinstance(expected, bool):
                                self.assertEqual(bool(actual), expected)
                            elif isinstance(expected, (int, float)):
                                self.assertAlmostEqual(float(actual), float(expected), places=10)
                            else:
                                self.assertEqual(actual, expected)
                from openpyxl import load_workbook
                formatted = load_workbook(output / "benchmark.xlsx")
                self.assertEqual(formatted["Runs"].freeze_panes, "A2")
                self.assertIsNotNone(formatted["Runs"].auto_filter.ref)
                pass_rate_column = run_frame.columns.get_loc("pass_rate") + 1
                self.assertEqual(formatted["Runs"].cell(2, pass_rate_column).number_format, "0.00%")

    def test_aggregation_is_idempotent_for_metrics_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            self._write_metrics_run(runs, 1, status="AUT_FAILED",
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
            self.assertTrue(pd.isna(second[0].iloc[0]["total_tokens"]))
            self.assertEqual(second[2].iloc[0]["total_runs"], 1)
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
                             {"runs.csv", "checks.csv", "summary.csv", "benchmark.xlsx"})
            self.assertEqual(list(pd.read_csv(output / "runs.csv").columns), run_frame.columns.tolist())
            with pd.ExcelFile(output / "benchmark.xlsx") as workbook:
                # I fogli di base devono essere presenti (possono esserci anche fogli extra)
                self.assertIn("Runs", workbook.sheet_names)
                self.assertIn("Checks", workbook.sheet_names)
                self.assertIn("Summary", workbook.sheet_names)
                self.assertTrue(pd.read_excel(workbook, sheet_name="Runs").empty)

    def test_single_workbook_separates_all_scenario_blocks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            self._write_metrics_run(runs, 1, status="COMPLETED", pass_rate=1.0,
                                    input_tokens=10, output_tokens=5, scenario="example_dns_001")
            self._write_metrics_run(runs, 1, status="COMPLETED", pass_rate=0.5,
                                    input_tokens=20, output_tokens=8, scenario="example_dns_002")
            output = root / "results"
            aggregate(runs, output)

            from openpyxl import load_workbook
            workbook = load_workbook(output / "benchmark.xlsx", data_only=True)
            # Verifica che i fogli di base siano presenti (ci sono anche fogli extra)
            self.assertIn("Runs", workbook.sheetnames)
            self.assertIn("Checks", workbook.sheetnames)
            self.assertIn("Summary", workbook.sheetnames)
            runs_sheet = workbook["Runs"]
            # experiment_id è la prima colonna; scenario è la seconda
            scenario_col = [cell.value for cell in runs_sheet[1]].index("Lab") + 1
            self.assertEqual(runs_sheet.cell(2, scenario_col).value, "example_dns_001")
            self.assertEqual(runs_sheet.cell(3, scenario_col).value, "example_dns_002")
            run_id_column = [cell.value for cell in runs_sheet[1]].index("ID") + 1
            self.assertEqual(runs_sheet.cell(2, run_id_column).value, "example_dns_001__T1__auto__r001")
            self.assertEqual(runs_sheet.cell(3, run_id_column).value, "example_dns_002__T1__auto__r001")
            self.assertEqual(runs_sheet["A1"].fill.fgColor.rgb[-6:], "2F5597")
            self.assertEqual(runs_sheet.freeze_panes, "A2")

    def test_summary_keeps_prompt_types_in_separate_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            first = self._write_metrics_run(runs, 1, status="COMPLETED", pass_rate=1.0,
                                            input_tokens=10, output_tokens=5)
            second = root / "runs/example_dns_001/T2/auto/r001"
            second.parent.mkdir(parents=True)
            import shutil
            shutil.copytree(first, second)
            metrics_path = second / "evaluation/metrics.json"
            metrics = json.loads(metrics_path.read_text())
            metrics["prompt_type"] = "T2"
            metrics["run_id"] = "example_dns_001__T2__auto__r001"
            metrics_path.write_text(json.dumps(metrics))
            _, _, summary = aggregate(runs, root / "results")
            self.assertEqual(set(summary["T"]), {"T1", "T2"})
            self.assertEqual(summary["total_runs"].tolist(), [1, 1])

    def test_failed_report_is_not_added_twice_and_summary_has_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            first = self._write_metrics_run(runs, 1, status="COMPLETED", pass_rate=0.0,
                                            input_tokens=10, output_tokens=2)
            failed_report = first / "results/lab/lab_result_failed.csv"
            failed_report.write_text("Test Description,Passed,Reason\nsample-1,False,failure\n")
            self._write_metrics_run(runs, 2, status="COMPLETED", pass_rate=1.0,
                                    input_tokens=20, output_tokens=4)
            _, checks, summary = aggregate(runs, root / "results")
            self.assertEqual(len(checks), 2)
            row = summary.iloc[0]
            self.assertEqual(row["total_runs"], 2)
            self.assertEqual(row["task_success_runs"], 1)
            self.assertEqual(row["task_failed_runs"], 1)
            self.assertEqual(row["mean_pass_rate"], 0.5)
            self.assertEqual(row["median_pass_rate"], 0.5)
            self.assertAlmostEqual(row["stdev_pass_rate"], 2 ** -0.5)
            self.assertTrue(pd.isna(row["mean_total_tokens"]))

if __name__ == "__main__":
    unittest.main()


