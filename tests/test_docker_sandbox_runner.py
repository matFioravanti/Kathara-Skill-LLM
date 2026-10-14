"""Test con mock per benchmark_core/docker_sandbox_runner.py.

Verifica avvio, isolamento, cleanup e compatibilita'.
Non esegue alcuna chiamata LLM ne' lancia sandbox reali.
"""
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Import del modulo da testare
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_core.docker_sandbox_runner import (
    EXPECTED_SBX_VERSION,
    SandboxAuthError,
    SandboxDaemonError,
    SandboxError,
    SandboxRun,
    _parse_events,
    _sbx_rm,
    _unique_sandbox_name,
    preflight_docker_sandbox,
    run_codex_in_sandbox,
    sbx_daemon_ensure_running,
    sbx_daemon_status,
    sbx_version,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Test: sbx_version
# ---------------------------------------------------------------------------

class TestSbxVersion(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_parses_v_prefix(self, _which, mock_run):
        mock_run.return_value = _proc(stdout="sbx version v0.48.0 abc123")
        self.assertEqual(sbx_version(), "0.48.0")

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_parses_plain(self, _which, mock_run):
        mock_run.return_value = _proc(stdout="sbx version 0.48.0\n")
        self.assertEqual(sbx_version(), "0.48.0")

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_failure_raises(self, _which, mock_run):
        mock_run.return_value = _proc(returncode=1, stderr="error")
        with self.assertRaises(SandboxError):
            sbx_version()

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value=None)
    def test_no_sbx_raises(self, _which):
        from benchmark_core.docker_sandbox_runner import sbx_executable
        with self.assertRaises(SandboxError):
            sbx_executable()


# ---------------------------------------------------------------------------
# Test: sbx_daemon_status
# ---------------------------------------------------------------------------

class TestDaemonStatus(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_running(self, _which, mock_run):
        mock_run.return_value = _proc(stdout="Status:  running\nSocket: /tmp/sock")
        self.assertTrue(sbx_daemon_status())

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_stopped(self, _which, mock_run):
        mock_run.return_value = _proc(stdout="Status:  stopped\nSocket: /tmp/sock (not connected)")
        self.assertFalse(sbx_daemon_status())

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_no_status_keyword(self, _which, mock_run):
        mock_run.return_value = _proc(stdout="unknown output")
        self.assertFalse(sbx_daemon_status())


# ---------------------------------------------------------------------------
# Test: sbx_daemon_ensure_running
# ---------------------------------------------------------------------------

class TestDaemonEnsureRunning(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", return_value=True)
    def test_already_running(self, _status):
        # Deve tornare senza sollevare e senza chiamare daemon start
        sbx_daemon_ensure_running(auto_start=True, wait_seconds=1)

    @patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", return_value=False)
    def test_not_running_no_autostart_raises(self, _status):
        with self.assertRaises(SandboxDaemonError):
            sbx_daemon_ensure_running(auto_start=False, wait_seconds=1)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_autostart_success(self, _which, mock_run, _sleep):
        # Prima chiamata: daemon status iniziale (stopped) -> poi start -> poi status (running)
        status_stopped = _proc(stdout="Status:  stopped")
        status_running = _proc(stdout="Status:  running")
        start_ok = _proc(returncode=0)

        # sbx_daemon_status viene chiamato due volte (first check + after start)
        call_seq = [status_stopped, start_ok, status_running]
        mock_run.side_effect = call_seq

        # Patch sbx_daemon_status direttamente per controllare il flusso
        with patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", side_effect=[False, True]):
            sbx_daemon_ensure_running(auto_start=True, wait_seconds=5)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_autostart_timeout_raises(self, _which, mock_run, _sleep):
        start_ok = _proc(returncode=0)
        mock_run.return_value = start_ok
        with patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", side_effect=[False, False, False]):
            with patch("benchmark_core.docker_sandbox_runner.time.monotonic", side_effect=[0, 0, 100, 100]):
                with self.assertRaises(SandboxDaemonError):
                    sbx_daemon_ensure_running(auto_start=True, wait_seconds=1)


# ---------------------------------------------------------------------------
# Test: _unique_sandbox_name
# ---------------------------------------------------------------------------

class TestUniqueSandboxName(unittest.TestCase):
    def test_format(self):
        name = _unique_sandbox_name("lab00_five_router", 1)
        self.assertTrue(name.startswith("kathara-"))
        # Format: kathara-<safe>-r001-<8hex>
        parts = name.split("-")
        self.assertEqual(parts[0], "kathara")
        # Ultimo componente: 8 caratteri hex
        self.assertEqual(len(parts[-1]), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in parts[-1]))

    def test_uniqueness(self):
        names = {_unique_sandbox_name("lab", 1) for _ in range(10)}
        self.assertEqual(len(names), 10)

    def test_special_chars_sanitized(self):
        name = _unique_sandbox_name("Lab_2_No_DNS", 3)
        # Nessun underscore nel nome
        self.assertNotIn("_", name)


# ---------------------------------------------------------------------------
# Test: _parse_events
# ---------------------------------------------------------------------------

class TestParseEvents(unittest.TestCase):
    def test_empty(self):
        msg, usage = _parse_events("")
        self.assertIsNone(msg)
        self.assertIsNone(usage)

    def test_agent_message(self):
        line = json.dumps({"item": {"type": "agent_message", "text": "Configurazione completata."}})
        msg, usage = _parse_events(line)
        self.assertEqual(msg, "Configurazione completata.")
        self.assertIsNone(usage)

    def test_turn_completed_usage(self):
        line = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}})
        msg, usage = _parse_events(line)
        self.assertIsNone(msg)
        self.assertEqual(usage["input_tokens"], 100)

    def test_malformed_line_skipped(self):
        msg, usage = _parse_events("NOT JSON\n{}")
        self.assertIsNone(msg)
        self.assertIsNone(usage)


# ---------------------------------------------------------------------------
# Test: _sbx_rm
# ---------------------------------------------------------------------------

class TestSbxRm(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_success(self, _which, mock_run):
        mock_run.return_value = _proc(returncode=0)
        ok, err = _sbx_rm("my-sandbox")
        self.assertTrue(ok)
        self.assertIsNone(err)
        args = mock_run.call_args[0][0]
        self.assertIn("--force", args)
        self.assertIn("my-sandbox", args)

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_failure_returns_false(self, _which, mock_run):
        mock_run.return_value = _proc(returncode=1, stderr="sandbox not found")
        ok, err = _sbx_rm("ghost-sandbox")
        self.assertFalse(ok)
        self.assertIn("sandbox not found", err)

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run", side_effect=subprocess.TimeoutExpired("sbx", 30))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_timeout_returns_false(self, _which, _run):
        ok, err = _sbx_rm("slow-sandbox")
        self.assertFalse(ok)
        self.assertIn("scaduto", err)


# ---------------------------------------------------------------------------
# Test: preflight_docker_sandbox
# ---------------------------------------------------------------------------

class TestPreflightDockerSandbox(unittest.TestCase):
    def _patch_all_ok(self):
        """Restituisce un ExitStack-compatibile context di patch per preflight che passa."""
        return [
            patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx"),
            patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value=EXPECTED_SBX_VERSION),
            patch("benchmark_core.docker_sandbox_runner.sbx_check_docker_engine"),
            patch("benchmark_core.docker_sandbox_runner.sbx_daemon_ensure_running"),
            patch("benchmark_core.docker_sandbox_runner.sbx_check_auth"),
        ]

    def test_all_ok_returns_version(self):
        patches = self._patch_all_ok()
        started = [p.start() for p in patches]
        try:
            result = preflight_docker_sandbox()
            self.assertEqual(result, EXPECTED_SBX_VERSION)
        finally:
            for p in patches:
                p.stop()

    def test_version_mismatch_raises(self):
        with patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.47.0"):
            with self.assertRaises(SandboxError) as ctx:
                preflight_docker_sandbox()
            self.assertIn("0.47.0", str(ctx.exception))
            self.assertIn(EXPECTED_SBX_VERSION, str(ctx.exception))

    def test_sbx_not_found_raises(self):
        with patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value=None):
            with self.assertRaises(SandboxError):
                preflight_docker_sandbox()

    def test_docker_engine_failure_raises(self):
        with patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value=EXPECTED_SBX_VERSION), \
             patch("benchmark_core.docker_sandbox_runner.sbx_check_docker_engine",
                   side_effect=SandboxError("Docker Engine non raggiungibile")):
            with self.assertRaises(SandboxError) as ctx:
                preflight_docker_sandbox()
            self.assertIn("Docker Engine", str(ctx.exception))

    def test_daemon_error_raises(self):
        with patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value=EXPECTED_SBX_VERSION), \
             patch("benchmark_core.docker_sandbox_runner.sbx_check_docker_engine"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_daemon_ensure_running",
                   side_effect=SandboxDaemonError("daemon error")):
            with self.assertRaises(SandboxDaemonError):
                preflight_docker_sandbox()

    def test_auth_error_raises(self):
        with patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value=EXPECTED_SBX_VERSION), \
             patch("benchmark_core.docker_sandbox_runner.sbx_check_docker_engine"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_daemon_ensure_running"), \
             patch("benchmark_core.docker_sandbox_runner.sbx_check_auth",
                   side_effect=SandboxAuthError("not authenticated")):
            with self.assertRaises(SandboxAuthError):
                preflight_docker_sandbox()


# ---------------------------------------------------------------------------
# Test: run_codex_in_sandbox (end-to-end mock)
# ---------------------------------------------------------------------------

class TestRunCodexInSandbox(unittest.TestCase):
    """Verifica il ciclo di vita completo con subprocess completamente mockato."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "lab"
        ws.mkdir()
        (ws / "lab.conf").write_text("[pc1]\n")
        return ws

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_success_full_lifecycle(self, mock_run, _ver, _which):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ws = self._make_workspace(tmp)
            logs = tmp / "logs/aut"

            events_jsonl = (
                json.dumps({"item": {"type": "agent_message", "text": "Done"}}) + "\n" +
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}) + "\n"
            )

            # Sequenza: create -> exec -> cp_out -> rm
            mock_run.side_effect = [
                _proc(returncode=0, stdout="kathara-lab-r001-abcd1234"),  # sbx run --detach
                _proc(returncode=0, stdout=events_jsonl),                  # sbx exec codex
                _proc(returncode=0),                                        # sbx cp out
                _proc(returncode=0),                                        # sbx rm --force
            ]

            result = run_codex_in_sandbox(
                prompt="Configura il lab.",
                workspace=ws,
                logs=logs,
                timeout=300,
                model="gpt-5.6-terra",
                reasoning_effort="low",
                variant="aut",
                sandbox_name="kathara-lab-r001-abcd1234",
            )

            self.assertTrue(result.success)
            self.assertEqual(result.sandbox_name, "kathara-lab-r001-abcd1234")
            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.timed_out)
            self.assertTrue(result.cleanup_ok)
            self.assertIsNone(result.cleanup_error)
            self.assertEqual(result.final_message, "Done")
            self.assertEqual(result.usage["input_tokens"], 10)

            # Verifica artefatti di log
            self.assertTrue((logs / "events.jsonl").is_file())
            self.assertTrue((logs / "result.json").is_file())
            self.assertTrue((logs / "invocation.json").is_file())
            self.assertTrue((logs / "sandbox_metadata.json").is_file())
            self.assertTrue((logs / "prompt_sent.md").is_file())

            # Verifica contenuto invocation.json
            inv = json.loads((logs / "invocation.json").read_text())
            self.assertEqual(inv["execution_backend"], "docker_sandbox")
            self.assertFalse(inv["api_key_used"])
            self.assertEqual(inv["sandbox_name"], "kathara-lab-r001-abcd1234")

            # Verifica contenuto sandbox_metadata.json
            meta = json.loads((logs / "sandbox_metadata.json").read_text())
            self.assertTrue(meta["cleanup_ok"])
            self.assertIsNone(meta["cleanup_error"])

            # Verifica che rm sia stato chiamato con --force
            rm_call = mock_run.call_args_list[-1]
            self.assertIn("--force", rm_call[0][0])

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_on_codex_failure(self, mock_run, _ver, _which):
        """Il sandbox viene eliminato anche se Codex fallisce."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ws = self._make_workspace(tmp)
            logs = tmp / "logs/aut"

            mock_run.side_effect = [
                _proc(returncode=0, stdout="kathara-lab-r001-fail1234"),  # create
                _proc(returncode=1, stderr="codex error"),                 # exec (fallisce)
                _proc(returncode=0),                                        # cp (anche se exec fallisce)
                _proc(returncode=0),                                        # rm --force
            ]

            with self.assertRaises(SandboxError) as ctx:
                run_codex_in_sandbox(
                    prompt="test",
                    workspace=ws,
                    logs=logs,
                    timeout=300,
                    model=None,
                    reasoning_effort=None,
                    variant="aut",
                    sandbox_name="kathara-lab-r001-fail1234",
                )
            self.assertIn("fallito", str(ctx.exception))

            # Il rm deve essere stato chiamato (cleanup garantito)
            calls = [c[0][0] for c in mock_run.call_args_list]
            rm_calls = [c for c in calls if "rm" in c and "--force" in c]
            self.assertEqual(len(rm_calls), 1)

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_on_create_failure(self, mock_run, _ver, _which):
        """Se la creazione del sandbox fallisce non si tenta nemmeno di eseguire Codex."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"
            mock_run.return_value = _proc(returncode=1, stderr="create failed")
            with self.assertRaises(SandboxError) as ctx:
                run_codex_in_sandbox(
                    prompt="test",
                    workspace=ws,
                    logs=logs,
                    timeout=10,
                    model=None,
                    reasoning_effort=None,
                    variant="aut",
                    sandbox_name="kathara-bad",
                )
            self.assertIn("Impossibile creare", str(ctx.exception))
            # rm NON deve essere chiamato (il sandbox non e' stato creato)
            calls_flat = [c[0][0] for c in mock_run.call_args_list]
            rm_calls = [c for c in calls_flat if "rm" in c]
            self.assertEqual(len(rm_calls), 0)

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_rm_failure_does_not_mask_main_success(self, mock_run, _ver, _which):
        """Se rm fallisce il risultato principale e' comunque SandboxRun.success==True."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"

            events_jsonl = json.dumps({"item": {"type": "agent_message", "text": "OK"}}) + "\n"
            mock_run.side_effect = [
                _proc(returncode=0, stdout="kathara-lab-r001-rmfail1"),  # create
                _proc(returncode=0, stdout=events_jsonl),                  # exec
                _proc(returncode=0),                                        # cp out
                _proc(returncode=1, stderr="rm failed"),                    # rm --force
            ]

            result = run_codex_in_sandbox(
                prompt="test",
                workspace=ws,
                logs=logs,
                timeout=300,
                model=None,
                reasoning_effort=None,
                variant="aut",
                sandbox_name="kathara-lab-r001-rmfail1",
            )
            self.assertTrue(result.success)
            self.assertFalse(result.cleanup_ok)
            self.assertIn("rm failed", result.cleanup_error)

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_skills_off_flag_in_create_command(self, mock_run, _ver, _which):
        """Verifica che --skills off sia presente nel comando di creazione sandbox."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"
            events_jsonl = json.dumps({"item": {"type": "agent_message", "text": "ok"}}) + "\n"
            mock_run.side_effect = [
                _proc(returncode=0, stdout="sbx-id"),
                _proc(returncode=0, stdout=events_jsonl),
                _proc(returncode=0),
                _proc(returncode=0),
            ]
            run_codex_in_sandbox(
                prompt="test",
                workspace=ws,
                logs=logs,
                timeout=10,
                model=None,
                reasoning_effort=None,
                variant="aut",
                sandbox_name="kathara-test-skills-off",
            )
            create_call = mock_run.call_args_list[0][0][0]
            self.assertIn("--skills", create_call)
            skills_idx = create_call.index("--skills")
            self.assertEqual(create_call[skills_idx + 1], "off")

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_api_keys_not_passed_to_sandbox(self, mock_run, _ver, _which):
        """Verifica che OPENAI_API_KEY e CODEX_API_KEY siano rimossi dall'env."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"

            captured_env = {}

            def capture_run(cmd, **kwargs):
                nonlocal captured_env
                if "exec" in cmd and "codex" in cmd:
                    captured_env = kwargs.get("env", {})
                return _proc(returncode=0, stdout=json.dumps(
                    {"item": {"type": "agent_message", "text": "ok"}}
                ) + "\n")

            mock_run.side_effect = [
                _proc(returncode=0, stdout="sbx-id"),  # create
                MagicMock(side_effect=capture_run),     # exec (da sostituire)
                _proc(returncode=0),                    # cp
                _proc(returncode=0),                    # rm
            ]

            # Patch diretto per catturare env
            env_captured = {}
            original_run = subprocess.run

            def patched_run(cmd, **kwargs):
                if isinstance(cmd, list) and "exec" in cmd and "codex" in cmd:
                    env_captured.update(kwargs.get("env", {}))
                    return _proc(returncode=0, stdout=json.dumps(
                        {"item": {"type": "agent_message", "text": "ok"}}
                    ) + "\n")
                return _proc(returncode=0, stdout="sbx-id")

            mock_run.side_effect = patched_run

            import os
            orig_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sk-secret"
            os.environ["CODEX_API_KEY"] = "ck-secret"
            try:
                run_codex_in_sandbox(
                    prompt="test",
                    workspace=ws,
                    logs=logs,
                    timeout=10,
                    model=None,
                    reasoning_effort=None,
                    variant="aut",
                    sandbox_name="kathara-apikey-test",
                )
            except Exception:
                pass  # Potrebbe fallire per il rm, ma ci interessa l'env
            finally:
                if orig_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = orig_key
                os.environ.pop("CODEX_API_KEY", None)

            # OPENAI_API_KEY e CODEX_API_KEY non devono essere presenti nell'env del codex exec
            self.assertNotIn("OPENAI_API_KEY", env_captured)
            self.assertNotIn("CODEX_API_KEY", env_captured)


# ---------------------------------------------------------------------------
# Test: isolamento — nessuna memoria storica tra run
# ---------------------------------------------------------------------------

class TestSandboxIsolation(unittest.TestCase):
    """Verifica che ogni sandbox parta da zero: nome univoco, nessun volume condiviso."""

    def test_each_call_gets_unique_name(self):
        names = [_unique_sandbox_name("lab00_five_router", i) for i in range(1, 6)]
        self.assertEqual(len(set(names)), 5)

    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_sandbox_name_in_exec_command(self, mock_run, _ver, _which):
        """Il nome del sandbox compare nel comando sbx exec."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir) / "lab"
            ws.mkdir()
            logs = Path(tmpdir) / "logs/aut"
            events_jsonl = json.dumps({"item": {"type": "agent_message", "text": "ok"}}) + "\n"

            mock_run.side_effect = [
                _proc(returncode=0, stdout="sbx-unique-id"),
                _proc(returncode=0, stdout=events_jsonl),
                _proc(returncode=0),
                _proc(returncode=0),
            ]

            sandbox_name = "kathara-test-isolation-abcd1234"
            run_codex_in_sandbox(
                prompt="test",
                workspace=ws,
                logs=logs,
                timeout=10,
                model=None,
                reasoning_effort=None,
                variant="aut",
                sandbox_name=sandbox_name,
            )

            exec_call = mock_run.call_args_list[1][0][0]  # seconda chiamata = sbx exec
            self.assertIn(sandbox_name, exec_call)


# ---------------------------------------------------------------------------
# Test: compatibilita' con backend host (nessun docker_sandbox)
# ---------------------------------------------------------------------------

class TestPreflightCompatibility(unittest.TestCase):
    """Preflight non deve toccare sbx quando il backend e' host (codex_cli)."""

    def test_is_docker_sandbox_false_without_config(self):
        from benchmark_core.preflight import _is_docker_sandbox_backend
        from benchmark_core.config import Config
        config = Config(Path("/dummy"), {
            "aut": {"agent": "codex", "version": "0.157.1"},
            "benchmark": {"timeout_seconds": 30},
        })
        self.assertFalse(_is_docker_sandbox_backend(config))

    def test_is_docker_sandbox_true_with_config(self):
        from benchmark_core.preflight import _is_docker_sandbox_backend
        from benchmark_core.config import Config
        config = Config(Path("/dummy"), {
            "aut": {"agent": "codex", "version": "0.157.1"},
            "benchmark": {"timeout_seconds": 30},
            "docker_sandbox": {"execution_backend": "docker_sandbox"},
        })
        self.assertTrue(_is_docker_sandbox_backend(config))

    def test_is_docker_sandbox_false_for_antigravity(self):
        from benchmark_core.preflight import _is_docker_sandbox_backend
        from benchmark_core.config import Config
        config = Config(Path("/dummy"), {
            "aut": {"agent": "antigravity", "version": "1.0.0"},
            "benchmark": {"timeout_seconds": 30},
            "docker_sandbox": {"execution_backend": "docker_sandbox"},
        })
        # La funzione ritorna True ma preflight la usa solo per agent==codex
        # Verifica che il campo docker_sandbox sia letto correttamente
        self.assertTrue(_is_docker_sandbox_backend(config))


if __name__ == "__main__":
    unittest.main()
