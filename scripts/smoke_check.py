#!/usr/bin/env python3
"""Smoke offline, artefatti esclusivamente temporanei; nessun laboratorio avviato."""
from pathlib import Path
import ast
import importlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from benchmark_core.agent_factory import AGENTS, validate_agent
    from benchmark_core.aggregation import aggregate
    from benchmark_core.analysis import analyze
    from benchmark_core.checker_runner import parse_reports
    from benchmark_core.config import load_config, skill_paths
    from benchmark_core.codex_cli_runner import command_for
    from benchmark_core.diff_metrics import compute_diff
    from benchmark_core.scenario_loader import discover_scenarios
    from benchmark_core.workspace import component_versions, create_workspace, tree_hash, write_json

    for module in ("kathara_lab_checker", "pandas", "yaml"):
        importlib.import_module(module)
    print("OK import:", json.dumps(component_versions()))
    config = load_config(ROOT / "benchmark.yaml")
    scenarios = discover_scenarios(ROOT / "scenarios")
    assert scenarios, "Serve almeno uno scenario per lo smoke"
    print("OK configurazione e discovery:", ", ".join(scenarios))
    assert AGENTS == {"codex": "codex_cli"}
    validate_agent("codex")
    print("OK backend Codex CLI locale")
    subprocess.run([sys.executable, "-m", "kathara_lab_checker", "--version"], check=True)
    for directory in (ROOT / "benchmark_core", ROOT / "scripts"):
        for path in directory.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    print("OK sintassi Python")
    with tempfile.TemporaryDirectory(prefix="kathara-benchmark-smoke-") as temporary:
        tmp = Path(temporary)
        summary, details = aggregate(tmp / "empty", tmp / "results")
        assert summary.empty and details.empty
        assert analyze(tmp / "results").iloc[0]["runs"] == 0
        scenario = next(iter(scenarios.values()))
        before = tree_hash(scenario.lab)
        run = create_workspace(tmp / "runs", scenario, "codex", 1)
        lab = run / "lab"
        assert tree_hash(lab) == before
        (lab / "smoke.txt").write_text("one\ntwo\n")
        diff = compute_diff(scenario.lab, lab)
        assert diff["files_created"] == 1 and diff["lines_added"] == 2
        assert tree_hash(scenario.lab) == before
        command = command_for(workspace=lab, model=None, reasoning_effort=None)
        assert command[1:3] == ("exec", "--json") and command[-1] == "-"
        print("OK workspace isolato, diff e aggregazione/analisi vuote")

        # Usa i writer REALI del checker, senza emulare il formato CSV.
        from kathara_lab_checker.csv_utils import write_result_to_csv, write_final_results_to_csv
        from kathara_lab_checker.model.SuccessfulCheck import SuccessfulCheck
        from kathara_lab_checker.model.FailedCheck import FailedCheck
        from kathara_lab_checker.model.TestCollector import TestCollector
        reports = run / "results"
        (reports / "lab").mkdir(parents=True, exist_ok=True)
        checks = [SuccessfulCheck("Checking correctness of DNS records"),
                  FailedCheck("HTTP check 'http://example.test' on client status", "Expected 200, got 404")]
        collector = TestCollector()
        collector.add_check_results("lab", checks)
        write_result_to_csv(checks, str(reports / "lab"))
        write_final_results_to_csv(collector, str(reports))
        checker, rows = parse_reports(reports)
        assert checker["task_success"] is False and checker["check_pass_rate"] == 0.5 and len(rows) == 2
        write_json(run / "manifest.json", {"run_id": run.name, "scenario_id": scenario.scenario_id,
                   "repetition": 1, "agent": "codex", "pipeline_state": "COMPLETED",
                   "aut_execution_success": True, "correction_generation_success": True,
                   "checker_execution_success": True, "task_success": True})
        write_json(run / "logs/checker_execution.json", {"returncode": 0, "timed_out": False})
        summary, details = aggregate(tmp / "runs", tmp / "results")
        assert not bool(summary.iloc[0]["task_success"]) and len(details) == 2
        assert analyze(tmp / "results").iloc[0]["task_success_rate"] == 0
        print("OK report checker reali, task_success derivato dal checker, aggregazione e analisi")
    missing = [str(p.relative_to(ROOT)) for p in skill_paths(config).values() if not p.is_file()]
    print("Skill esterne mancanti:", ", ".join(missing) if missing else "nessuna")
    print("SMOKE OK; nessuna chiamata LLM/Docker eseguita, artefatti temporanei rimossi.")


if __name__ == "__main__":
    main()
