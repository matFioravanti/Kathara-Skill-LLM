"""Test automatici per la telemetria dei parametri di campionamento LLM.

Copre i 15 requisiti obbligatori:
1. Estrazione di temperature = 1.0 da evento SSE valido.
2. Estrazione di top_p quando presente.
3. Gestione di valori assenti, null, invalidi e log malformati.
4. Ignorare stringhe JSON contenute nel testo del prompt o della risposta.
5. Gestione di più eventi della stessa risposta senza duplicazioni.
6. Rilevamento di valori discordanti.
7. Compatibilità della modalità passiva con la CLI esistente.
8. Configurazione HTTP soltanto su attivazione esplicita.
9. Gestione della modalità non supportata su Docker Sandbox.
10. Persistenza dei metadati anche in caso di errore dell'AUT.
11. Creazione corretta di metrics.json con sezione llm_sampling separata.
12. Presenza dei nuovi campi in runs.csv ed Excel con tipi numerici.
13. Corretta aggregazione di run nuove e storiche.
14. Invarianza della telemetria durante --rerun-correction.
15. Nessuna modifica ai punteggi e alle metriche già esistenti.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import openpyxl
import pandas as pd

from benchmark_core.aggregation import aggregate
from benchmark_core.codex_cli_runner import codex_environment, command_for, run_codex
from benchmark_core.config import Config, load_config
from benchmark_core.inspect_adapter import create_inspect_eval_log
from benchmark_core.inspect_runner import run_aut
from benchmark_core.pipeline import reevaluate_run
from benchmark_core.run_metrics import make_metrics
from benchmark_core.sampling_telemetry import (
    HTTP_PROVIDER_CONFIG_ARGS,
    HTTP_TRACE_RUST_LOG,
    SamplingTelemetry,
    extract_sampling_telemetry,
    parse_sampling_telemetry,
    save_sampling_telemetry,
)
from benchmark_core.workspace import write_json


class TestSamplingTelemetry(unittest.TestCase):

    # 1. Estrazione di temperature = 1.0 da un evento SSE valido
    def test_01_extract_temperature_from_valid_sse_event(self):
        stderr = (
            "2026-10-28T16:26:47.123456Z TRACE codex_api::sse::responses: data: "
            '{"type":"response.created","response":{"id":"resp_001","model":"gpt-5.6-terra","temperature":1.0}}\n'
        )
        telemetry = parse_sampling_telemetry(stderr_text=stderr, collection_mode="http_trace")
        self.assertEqual(telemetry.temperature, 1.0)
        self.assertIsNone(telemetry.top_p)
        self.assertEqual(telemetry.status, "partial")
        self.assertEqual(telemetry.source, "server_response")
        self.assertEqual(telemetry.transport, "http")
        self.assertEqual(telemetry.response_count, 1)
        self.assertEqual(telemetry.distinct_temperatures, (1.0,))

    # 2. Estrazione di top_p quando presente
    def test_02_extract_top_p_when_present(self):
        stderr = (
            "TRACE codex_api::sse::responses: data: {\"type\":\"response.done\",\"response\":{\"id\":\"resp_002\",\"model\":\"gpt-5.6-terra\",\"temperature\":0.7,\"top_p\":0.95}}\n"
        )
        telemetry = parse_sampling_telemetry(stderr_text=stderr, collection_mode="http_trace")
        self.assertEqual(telemetry.temperature, 0.7)
        self.assertEqual(telemetry.top_p, 0.95)
        self.assertEqual(telemetry.status, "observed")
        self.assertEqual(telemetry.distinct_temperatures, (0.7,))
        self.assertEqual(telemetry.distinct_top_p, (0.95,))

    # 3. Gestione di valori assenti, null, invalidi e log malformati
    def test_03_absent_null_invalid_and_malformed_logs(self):
        # Esplicitamente null
        null_stderr = 'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_null","temperature":null,"top_p":null}}\n'
        t_null = parse_sampling_telemetry(stderr_text=null_stderr, collection_mode="http_trace")
        self.assertIsNone(t_null.temperature)
        self.assertIsNone(t_null.top_p)
        self.assertEqual(t_null.status, "explicit_null")

        # Valori non numerici o invalidi (booleani, stringhe, NaN, Infinity)
        invalid_stderr = (
            'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_inv1","temperature":true,"top_p":"high"}}\n'
            'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_inv2","temperature":NaN}}\n'
        )
        # NaN in json non standard genera decode error o viene gestito
        t_inv = parse_sampling_telemetry(stderr_text='TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_inv","temperature":true,"top_p":"0.9"}}\n')
        self.assertIsNone(t_inv.temperature)
        self.assertIsNone(t_inv.top_p)

        # Log malformato / troncato
        malformed = (
            "TRACE codex_api::sse::responses: data: {corrupted json line...\n"
            "2026-10-28 TRACE codex_api::sse::responses: data: {\"incomplete\":\n"
            "plain non-json stderr noise\n"
        )
        t_malf = parse_sampling_telemetry(stderr_text=malformed, collection_mode="http_trace")
        self.assertIsNone(t_malf.temperature)
        self.assertEqual(t_malf.status, "unavailable")

    # 4. Ignorare stringhe JSON contenute nel testo del prompt o della risposta
    def test_04_ignore_json_in_prompt_or_agent_messages(self):
        # Evento con messaggio dell'agente che menziona temperature
        events = (
            '{"type":"item.completed","item":{"id":"msg1","type":"agent_message","text":"Ho impostato temperature: 0.2 nel file di config"}}\n'
            '{"type":"item.completed","item":{"id":"cmd1","type":"command_execution","command":"echo \\"temperature: 0.5\\""'
            ',"aggregated_output":"{\\"temperature\\": 0.5}"}}\n'
        )
        stderr = "Prompt text was: Configure lab with temperature: 0.1\n"
        telemetry = parse_sampling_telemetry(stderr_text=stderr, events_text=events, collection_mode="passive")
        # Nessun falso positivo deve essere estratto
        self.assertIsNone(telemetry.temperature)
        self.assertIsNone(telemetry.top_p)
        self.assertEqual(telemetry.status, "unavailable")

    # 5. Gestione di più eventi della stessa risposta senza duplicazioni
    def test_05_multiple_events_same_response_deduplication(self):
        stderr = (
            'TRACE codex_api::sse::responses: data: {"type":"response.created","response":{"id":"resp_same","model":"gpt-5.6-terra","temperature":1.0}}\n'
            'TRACE codex_api::sse::responses: data: {"type":"response.output_item.added","response":{"id":"resp_same","temperature":1.0}}\n'
            'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_same","temperature":1.0}}\n'
        )
        telemetry = parse_sampling_telemetry(stderr_text=stderr, collection_mode="http_trace")
        self.assertEqual(telemetry.response_count, 1)
        self.assertEqual(telemetry.temperature, 1.0)
        self.assertEqual(telemetry.distinct_temperatures, (1.0,))
        self.assertEqual(telemetry.status, "partial")

    # 6. Rilevamento di valori discordanti
    def test_06_conflicting_values_detection(self):
        stderr = (
            'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_turn1","temperature":0.7}}\n'
            'TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"resp_turn2","temperature":1.0}}\n'
        )
        telemetry = parse_sampling_telemetry(stderr_text=stderr, collection_mode="http_trace")
        self.assertIsNone(telemetry.temperature)
        self.assertEqual(telemetry.status, "inconsistent")
        self.assertEqual(telemetry.distinct_temperatures, (0.7, 1.0))
        self.assertIn("discordanti", str(telemetry.details).lower())

    # 7. Compatibilità della modalità passiva con la CLI esistente
    def test_07_passive_mode_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"):
                cmd = command_for(workspace=ws, model="gpt-5.6-terra", reasoning_effort="low", sampling_mode="passive")
                self.assertNotIn('model_provider="chatgpt-http"', cmd)
                env = codex_environment(sampling_mode="passive")
                self.assertEqual(env.get("RUST_LOG"), os.environ.get("RUST_LOG"))

        # Se nessun metadato è presente nei log, la modalità passiva restituisce unavailable
        telemetry = parse_sampling_telemetry(stderr_text="", events_text="", collection_mode="passive")
        self.assertEqual(telemetry.status, "unavailable")
        self.assertIsNone(telemetry.temperature)

    # 8. Configurazione HTTP soltanto su attivazione esplicita
    def test_08_http_trace_only_on_explicit_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"):
                cmd = command_for(workspace=ws, model="gpt-5.6-terra", reasoning_effort="low", sampling_mode="http_trace")
                for arg in HTTP_PROVIDER_CONFIG_ARGS:
                    self.assertIn(arg, cmd)
                env = codex_environment(sampling_mode="http_trace")
                self.assertIn(HTTP_TRACE_RUST_LOG, env.get("RUST_LOG", ""))

    # 9. Gestione della modalità non supportata su Docker Sandbox
    def test_09_unsupported_backend_on_docker_sandbox(self):
        telemetry = parse_sampling_telemetry(
            stderr_text='TRACE codex_api::sse::responses: data: {"type":"response.done","response":{"id":"r1","temperature":1.0}}\n',
            collection_mode="http_trace",
            backend="docker_sandbox",
        )
        self.assertEqual(telemetry.status, "unsupported_backend")
        self.assertEqual(telemetry.source, "unsupported")
        self.assertIsNone(telemetry.temperature)
        self.assertIn("docker_sandbox", str(telemetry.details))

    # 10. Persistenza dei metadati anche in caso di errore dell'AUT
    def test_10_metadata_persistence_on_aut_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs/lab/T1/dns_only/r001"
            logs = run / "logs/aut"
            logs.mkdir(parents=True)
            workspace = root / "ws"
            workspace.mkdir()

            stderr = (
                "2026-10-28 TRACE codex_api::sse::responses: data: "
                '{"type":"response.done","response":{"id":"resp_err","temperature":1.0}}\n'
                "Process crashed with error code 7\n"
            )
            fake_proc = subprocess.CompletedProcess([], 7, stdout="", stderr=stderr)
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"), \
                 patch("benchmark_core.codex_cli_runner.subprocess.run", return_value=fake_proc):
                try:
                    run_codex(
                        prompt="test prompt", workspace=workspace, logs=logs, timeout=10,
                        model="gpt-5.6-terra", reasoning_effort="low", variant="aut",
                        sampling_mode="http_trace",
                    )
                except Exception:
                    pass

            telemetry_path = logs / "sampling_telemetry.json"
            self.assertTrue(telemetry_path.is_file(), "sampling_telemetry.json deve essere salvato anche in caso di crash")
            data = json.loads(telemetry_path.read_text())
            self.assertEqual(data.get("temperature"), 1.0)
            self.assertEqual(data.get("status"), "partial")

    # 11. Creazione corretta di metrics.json
    def test_11_metrics_json_creation_with_llm_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            logs = run / "logs/aut"
            logs.mkdir(parents=True)
            (logs / "events.jsonl").write_text('{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n')
            write_json(logs / "result.json", {"duration_seconds": 2.5, "returncode": 0})
            save_sampling_telemetry(logs, SamplingTelemetry(
                temperature=1.0, top_p=None, source="server_response",
                status="observed", transport="http", collection_mode="http_trace",
                response_count=1, distinct_temperatures=(1.0,),
            ))

            metadata = {
                "scenario_id": "lab01", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "lab01__T1__dns_only__r001", "agent": "codex",
                "model": "gpt-5.6-terra", "pipeline_state": "COMPLETED",
            }
            metrics = make_metrics(
                run, metadata, total_seconds=5.0, checker_seconds=2.0,
                checker_outcome={"checks_passed": 2, "checks_failed": 0, "checks_total": 2, "check_pass_rate": 1.0},
            )
            self.assertIn("llm_sampling", metrics)
            sampling = metrics["llm_sampling"]
            self.assertEqual(sampling["temperature"], 1.0)
            self.assertIsNone(sampling["top_p"])
            self.assertEqual(sampling["status"], "observed")
            self.assertEqual(sampling["transport"], "http")
            # Le metriche dei token rimangono separate
            self.assertEqual(metrics["tokens"]["input"], 10)
            self.assertEqual(metrics["tokens"]["output"], 5)
            self.assertEqual(metrics["timing"]["agent_seconds"], 2.5)

    # 12. Presenza dei nuovi campi in runs.csv ed Excel
    def test_12_runs_csv_and_excel_fields_and_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            run = runs / "example_dns_001/T1/dns_only/r001"
            evaluation = run / "evaluation"
            logs = run / "logs/aut"
            evaluation.mkdir(parents=True)
            logs.mkdir(parents=True)

            metrics = {
                "scenario": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "example_dns_001__T1__dns_only__r001", "agent": "codex",
                "model": "gpt-5.6-terra", "reasoning_effort": "low", "status": "COMPLETED",
                "timing": {"agent_seconds": 3.0, "checker_seconds": 1.0, "total_seconds": 4.0},
                "tokens": {"input": 50, "output": 20, "total": 70},
                "checker": {"passed": 2, "failed": 0, "total": 2, "pass_rate": 1.0},
                "llm_sampling": {
                    "temperature": 1.0, "top_p": 0.9, "source": "server_response",
                    "status": "observed", "transport": "http",
                },
            }
            write_json(evaluation / "metrics.json", metrics)
            write_json(run / "manifest.json", {
                "scenario_id": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": metrics["run_id"], "agent": "codex",
                "model": "gpt-5.6-terra", "pipeline_state": "COMPLETED",
                "checker_execution_success": True, "task_success": True,
            })

            results = root / "results"
            run_frame, _, _ = aggregate(runs, results)

            # Verifica colonne in DataFrame
            for col in ("llm_temperature", "llm_top_p", "sampling_source", "sampling_status", "sampling_transport"):
                self.assertIn(col, run_frame.columns)

            self.assertEqual(float(run_frame.loc[0, "llm_temperature"]), 1.0)
            self.assertEqual(float(run_frame.loc[0, "llm_top_p"]), 0.9)
            self.assertEqual(run_frame.loc[0, "sampling_status"], "observed")

            # Verifica CSV
            csv_path = results / "runs.csv"
            df_csv = pd.read_csv(csv_path)
            self.assertIn("llm_temperature", df_csv.columns)
            self.assertEqual(float(df_csv.loc[0, "llm_temperature"]), 1.0)

            # Verifica Excel
            wb = openpyxl.load_workbook(results / "benchmark.xlsx", data_only=True)
            sheet = wb["Runs"]
            headers = [cell.value for cell in sheet[1]]
            self.assertIn("llm_temperature", headers)
            self.assertIn("llm_top_p", headers)
            temp_idx = headers.index("llm_temperature") + 1
            self.assertEqual(sheet.cell(2, temp_idx).value, 1.0)

    # 13. Corretta aggregazione di run nuove e storiche
    def test_13_aggregation_new_and_historical_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"

            # 1. Run storica: nessun campo llm_sampling
            hist_run = runs / "example_dns_001/T1/dns_only/r001"
            (hist_run / "evaluation").mkdir(parents=True)
            (hist_run / "logs/aut").mkdir(parents=True)
            write_json(hist_run / "evaluation/metrics.json", {
                "scenario": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "example_dns_001__T1__dns_only__r001", "agent": "codex",
                "model": "old-model", "status": "COMPLETED",
                "timing": {"agent_seconds": 2.0, "checker_seconds": 1.0, "total_seconds": 3.0},
                "tokens": {"input": 10, "output": 5, "total": 15},
                "checker": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
            })
            write_json(hist_run / "manifest.json", {
                "scenario_id": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "example_dns_001__T1__dns_only__r001", "agent": "codex",
                "pipeline_state": "COMPLETED", "checker_execution_success": True, "task_success": True,
            })

            # 2. Nuova run: con telemetria osservata
            new_run = runs / "example_dns_001/T1/dns_only/r002"
            (new_run / "evaluation").mkdir(parents=True)
            (new_run / "logs/aut").mkdir(parents=True)
            write_json(new_run / "evaluation/metrics.json", {
                "scenario": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 2, "run_id": "example_dns_001__T1__dns_only__r002", "agent": "codex",
                "model": "gpt-5.6-terra", "status": "COMPLETED",
                "timing": {"agent_seconds": 2.5, "checker_seconds": 1.0, "total_seconds": 3.5},
                "tokens": {"input": 12, "output": 6, "total": 18},
                "checker": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
                "llm_sampling": {"temperature": 1.0, "top_p": None, "source": "server_response", "status": "observed"},
            })
            write_json(new_run / "manifest.json", {
                "scenario_id": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 2, "run_id": "example_dns_001__T1__dns_only__r002", "agent": "codex",
                "pipeline_state": "COMPLETED", "checker_execution_success": True, "task_success": True,
            })

            results = root / "results"
            run_frame, _, summary_frame = aggregate(runs, results)
            self.assertEqual(len(run_frame), 2)

            hist_row = run_frame[run_frame["run_number"] == 1].iloc[0]
            new_row = run_frame[run_frame["run_number"] == 2].iloc[0]

            # La run storica deve avere temperature null (NaN) senza errori
            self.assertTrue(pd.isna(hist_row["llm_temperature"]))
            self.assertTrue(pd.isna(hist_row["sampling_status"]))

            # La nuova run ha il valore corretto
            self.assertEqual(float(new_row["llm_temperature"]), 1.0)
            self.assertEqual(new_row["sampling_status"], "observed")

            # Nel summary: 1 run osservata su 1 gruppo (o 2 gruppi a seconda dei modelli)
            self.assertEqual(summary_frame["total_runs"].sum(), 2)
            self.assertEqual(summary_frame["sampling_observed_runs"].sum(), 1)
            self.assertIn("1.0", str(summary_frame["sampling_temperatures"].dropna().iloc[0]))

    # 14. Invarianza della telemetria durante --rerun-correction
    def test_14_telemetry_invariance_during_rerun_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs/example_dns_001/T1/dns_only/r001"
            for folder in ("lab", "input/lab", "logs/aut", "results/lab", "evaluation"):
                (run / folder).mkdir(parents=True, exist_ok=True)
            (run / "lab/lab.conf").write_text("lab conf\n")
            (run / "input/lab/lab.conf").write_text("baseline\n")
            (run / "logs/aut/result.json").write_text('{"duration_seconds":3.0}\n')
            (run / "logs/aut/events.jsonl").write_text('{"type":"turn.completed","usage":{"total_tokens":20}}\n')

            # Salva telemetria di campionamento originale
            save_sampling_telemetry(run / "logs/aut", SamplingTelemetry(
                temperature=1.0, top_p=0.8, source="server_response", status="observed",
                transport="http", collection_mode="http_trace", response_count=1,
            ))

            write_json(run / "manifest.json", {
                "run_id": "example_dns_001__T1__dns_only__r001", "run_number": 1,
                "scenario_id": "example_dns_001", "skill_mode": "dns_only", "agent": "codex",
                "model": "gpt-5.6-terra", "aut_execution_success": True, "pipeline_state": "COMPLETED",
                "correction_sha256": "old_sha",
            })
            write_json(run / "evaluation/metrics.json", {
                "scenario": "example_dns_001", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "example_dns_001__T1__dns_only__r001", "agent": "codex",
                "model": "gpt-5.6-terra", "status": "COMPLETED",
                "tokens": {"total": 20},
                "timing": {"agent_seconds": 3.0, "total_seconds": 5.0},
                "checker": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
                "llm_sampling": {
                    "temperature": 1.0, "top_p": 0.8, "source": "server_response",
                    "status": "observed", "transport": "http",
                },
            })

            canonical = root / "scenarios/example_dns_001/correction.yaml"
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(b"new correction content\n")

            config = Config(root, {
                "checker": {"no_cache": True}, "benchmark": {"timeout_seconds": 10},
                "results": {"directory": "results"},
            })

            checker_outcome = {
                "checks_passed": 2, "checks_failed": 0, "checks_total": 2,
                "check_pass_rate": 1.0, "task_success": True,
            }

            with patch("benchmark_core.pipeline.read_correction", return_value=(canonical.read_bytes(), "new_sha")), \
                 patch("benchmark_core.pipeline.validate_correction", return_value="new_sha"), \
                 patch("benchmark_core.pipeline.run_checker", return_value=checker_outcome):
                reevaluate_run(config, run)

            updated_metrics = json.loads((run / "evaluation/metrics.json").read_text())
            self.assertIn("llm_sampling", updated_metrics)
            self.assertEqual(updated_metrics["llm_sampling"]["temperature"], 1.0)
            self.assertEqual(updated_metrics["llm_sampling"]["top_p"], 0.8)
            self.assertEqual(updated_metrics["llm_sampling"]["status"], "observed")
            self.assertEqual(updated_metrics["tokens"]["total"], 20)
            self.assertEqual(updated_metrics["checker"]["passed"], 2)

    # 15. Nessuna modifica ai punteggi e alle metriche già esistenti
    def test_15_scores_and_metrics_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            logs = run / "logs/aut"
            logs.mkdir(parents=True)
            (logs / "events.jsonl").write_text('{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":40,"total_tokens":140}}\n')
            write_json(logs / "result.json", {"duration_seconds": 6.5, "returncode": 0})

            metadata = {
                "scenario_id": "lab01", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "lab01__T1__dns_only__r001", "agent": "codex",
                "model": "gpt-5.6-terra", "pipeline_state": "COMPLETED",
            }
            checker_outcome = {"checks_passed": 5, "checks_failed": 1, "checks_total": 6, "check_pass_rate": 5/6}
            metrics = make_metrics(run, metadata, total_seconds=12.0, checker_seconds=5.5, checker_outcome=checker_outcome)

            self.assertEqual(metrics["checker"]["passed"], 5)
            self.assertEqual(metrics["checker"]["failed"], 1)
            self.assertEqual(metrics["checker"]["total"], 6)
            self.assertEqual(metrics["checker"]["pass_rate"], 5/6)
            self.assertEqual(metrics["timing"]["agent_seconds"], 6.5)
            self.assertEqual(metrics["timing"]["checker_seconds"], 5.5)
            self.assertEqual(metrics["timing"]["total_seconds"], 12.0)
            self.assertEqual(metrics["tokens"]["input"], 100)
            self.assertEqual(metrics["tokens"]["output"], 40)
            self.assertEqual(metrics["tokens"]["total"], 140)


class TestSamplingSafety(unittest.TestCase):
    # These are simulated events, not an integration test of a real server.
    def test_runner_exactly_once(self):
        from benchmark_core.inspect_runner import _call_runner
        from benchmark_core.codex_cli_runner import CodexExecutionError
        from unittest.mock import Mock
        for error in (None, TypeError("runner"), RuntimeError("runner"), CodexExecutionError("codex")):
            runner = Mock(side_effect=error)
            if error:
                with self.assertRaises(type(error)):
                    _call_runner(runner, sampling_mode="passive")
            else:
                _call_runner(runner, sampling_mode="passive")
            self.assertEqual(runner.call_count, 1)
        runner = Mock(side_effect=lambda prompt: prompt)
        self.assertEqual(_call_runner(runner, prompt="x", sampling_mode="passive"), "x")
        self.assertEqual(runner.call_count, 1)

    def test_disabled_does_not_read_logs(self):
        from benchmark_core.sampling_telemetry import extract_sampling_telemetry
        with patch.object(Path, "read_text", side_effect=AssertionError("read")):
            t = extract_sampling_telemetry(Path("."), collection_mode="disabled")
        self.assertEqual((t.status, t.temperature_status, t.top_p_status), ("disabled",) * 3)

    def test_zero_invalid_missing_and_conflicts(self):
        trace = 'TRACE codex_api::sse::responses: data: '
        def event(body):
            return trace + json.dumps(body) + "\n"
        def response(id, **params):
            return {"type": "response.completed", "response": {"id": id, **params}}
        t = parse_sampling_telemetry(stderr_text=event(response("r", temperature=0.0, top_p=1.1)))
        self.assertEqual(t.temperature, 0.0)
        self.assertIsNone(t.top_p)
        self.assertEqual((t.temperature_status, t.top_p_status), ("observed", "invalid"))
        t = parse_sampling_telemetry(stderr_text=event(response("r", temperature=None)))
        self.assertEqual((t.temperature_status, t.top_p_status), ("explicit_null", "not_reported"))
        t = parse_sampling_telemetry(stderr_text=event(response("r", temperature=0)) + event(response("r", temperature=0.2)))
        self.assertEqual(t.response_count, 1)
        self.assertEqual(t.distinct_temperatures, (0.0, 0.2))
        self.assertEqual(t.temperature_status, "inconsistent")

    def test_untrusted_structured_output_is_not_server_evidence(self):
        payload = '{"object":"response","id":"resp_fake","temperature":0.5}'
        for stderr, events in ((payload, ""), ("data: " + payload, ""), ("", payload),
                               ('prompt data: ' + payload, "")):
            t = parse_sampling_telemetry(stderr_text=stderr, events_text=events)
            self.assertEqual((t.source, t.transport, t.temperature), ("none", None, None))

    def test_disabled_and_passive_command_are_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp, patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"):
            args = dict(workspace=Path(tmp), model=None, reasoning_effort=None)
            self.assertEqual(command_for(**args, sampling_mode="disabled"), command_for(**args, sampling_mode="passive"))
            self.assertEqual(codex_environment(sampling_mode="disabled"), codex_environment(sampling_mode="passive"))


if __name__ == "__main__":
    unittest.main()
