"""Test con mock e test di integrazione per benchmark_core/docker_sandbox_runner.py.

Verifica:
- Creazione con sbx create (non sbx run --detach)
- Montaggio diretto del workspace (path assoluto host, no /workspace)
- Rimozione completa di sbx cp (bind mount diretto)
- Disabilitazione esplicita memoria Codex (--disable memories, -c memories=false)
- Cleanup rigoroso: errore di rimozione solleva SandboxCleanupError
- Preflight e auto-start Docker Engine su macOS
- Verifica reale del ciclo di vita con shell agent (zero token LLM)
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_core.docker_sandbox_runner import (
    DEFAULT_CODEX_SANDBOX_VERSION,
    EXPECTED_SBX_VERSION,
    SandboxArtifactError,
    SandboxAuthError,
    SandboxCleanupError,
    SandboxDaemonError,
    SandboxError,
    SandboxExecutionError,
    SandboxRun,
    _parse_events,
    _sbx_rm,
    _unique_sandbox_name,
    preflight_docker_sandbox,
    run_codex_in_sandbox,
    sbx_check_auth,
    sbx_check_docker_engine,
    sbx_check_sandbox_codex,
    sbx_daemon_ensure_running,
    sbx_daemon_status,
    sbx_executable,
    sbx_get_sandbox_id,
    sbx_host_codex_version,
    sbx_version,
)
from benchmark_core.run_metrics import codex_usage, make_metrics


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
        with self.assertRaises(SandboxError):
            sbx_executable()


# ---------------------------------------------------------------------------
# Test: sbx_daemon_status e ensure_running
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


class TestDaemonEnsureRunning(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", return_value=True)
    def test_already_running(self, _status):
        sbx_daemon_ensure_running(auto_start=True, wait_seconds=1)

    @patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", return_value=False)
    def test_not_running_no_autostart_raises(self, _status):
        with self.assertRaises(SandboxDaemonError):
            sbx_daemon_ensure_running(auto_start=False, wait_seconds=1)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_autostart_success(self, _which, mock_run, _sleep):
        mock_run.return_value = _proc(returncode=0)
        with patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", side_effect=[False, True]):
            sbx_daemon_ensure_running(auto_start=True, wait_seconds=5)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_autostart_timeout_raises(self, _which, mock_run, _sleep):
        mock_run.return_value = _proc(returncode=0)
        with patch("benchmark_core.docker_sandbox_runner.sbx_daemon_status", side_effect=[False, False, False]):
            with patch("benchmark_core.docker_sandbox_runner.time.monotonic", side_effect=[0, 0, 100, 100]):
                with self.assertRaises(SandboxDaemonError):
                    sbx_daemon_ensure_running(auto_start=True, wait_seconds=1)


# ---------------------------------------------------------------------------
# Test: sbx_check_docker_engine (Auto-start Docker Desktop)
# ---------------------------------------------------------------------------

class TestDockerEngineAutoStart(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/local/bin/docker")
    def test_docker_already_running(self, _which, mock_run):
        mock_run.return_value = _proc(returncode=0)
        sbx_check_docker_engine(auto_start=True, wait_seconds=5)
        # Solo docker info chiamato
        self.assertEqual(mock_run.call_count, 1)

    @patch("benchmark_core.docker_sandbox_runner.sys.platform", "darwin")
    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/local/bin/docker")
    def test_docker_auto_start_success(self, _which, mock_run, _sleep):
        # 1. docker info -> fallisce (rc=1)
        # 2. open -a Docker -> ok (rc=0)
        # 3. docker info retry -> ok (rc=0)
        mock_run.side_effect = [
            _proc(returncode=1, stderr="daemon not running"),
            _proc(returncode=0),
            _proc(returncode=0),
        ]
        sbx_check_docker_engine(auto_start=True, wait_seconds=10)
        calls = [c[0][0] for c in mock_run.call_args_list]
        self.assertIn(["open", "-a", "Docker"], calls)

    @patch("benchmark_core.docker_sandbox_runner.sys.platform", "darwin")
    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/local/bin/docker")
    def test_docker_auto_start_timeout_raises(self, _which, mock_run, _sleep):
        mock_run.side_effect = [
            _proc(returncode=1, stderr="down"),
            _proc(returncode=0),  # open -a Docker
            _proc(returncode=1, stderr="still down"),
        ]
        with patch("benchmark_core.docker_sandbox_runner.time.monotonic", side_effect=[0, 0, 100, 100]):
            with self.assertRaises(SandboxError) as ctx:
                sbx_check_docker_engine(auto_start=True, wait_seconds=5)
            self.assertIn("non e' diventato raggiungibile", str(ctx.exception))


# ---------------------------------------------------------------------------
# Test: sbx_check_sandbox_codex (Verifica interna Codex nel sandbox)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test: sbx_check_sandbox_codex (Verifica interna Codex nel sandbox)
# ---------------------------------------------------------------------------

class TestCheckSandboxCodex(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner._sbx_rm", return_value=(True, None))
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_check_sandbox_codex_success(self, _which, mock_run, _rm):
        # 1: create probe, 2: codex --version, 3: mem_test (features list), 4: policy check api.openai.com, 5: policy check chatgpt.com, 6: policy check unauthorized, 7: policy check google.com
        mock_run.side_effect = [
            _proc(returncode=0, stdout="Created sandbox sbx-probe"),
            _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
            _proc(returncode=0, stdout="memories  stable  false\nhooks  stable  true\n"),  # mem disabled in features list
            _proc(returncode=0, stdout=json.dumps({"allowed": True})),                        # api.openai.com allowed
            _proc(returncode=0, stdout=json.dumps({"allowed": True})),                        # chatgpt.com allowed
            _proc(returncode=1, stdout=json.dumps({"allowed": False})),                       # unauthorized-domain denied
            _proc(returncode=1, stdout=json.dumps({"allowed": False})),                       # google.com denied
        ]
        ver = sbx_check_sandbox_codex(expected_version="0.149.1")
        self.assertEqual(ver, "0.149.1")

    @patch("benchmark_core.docker_sandbox_runner._sbx_rm", return_value=(True, None))
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_check_sandbox_codex_version_mismatch(self, _which, mock_run, _rm):
        mock_run.side_effect = [
            _proc(returncode=0, stdout="Created sandbox sbx-probe"),
            _proc(returncode=0, stdout="codex-cli 0.148.0\n"),
        ]
        with self.assertRaises(SandboxError) as ctx:
            sbx_check_sandbox_codex(expected_version="0.149.1")
        self.assertIn("version mismatch", str(ctx.exception))

    @patch("benchmark_core.docker_sandbox_runner._sbx_rm", return_value=(True, None))
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_check_sandbox_codex_memory_flags_unsupported(self, _which, mock_run, _rm):
        mock_run.side_effect = [
            _proc(returncode=0, stdout="Created sandbox sbx-probe"),
            _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
            _proc(returncode=1, stderr="unrecognized argument --disable"),
        ]
        with self.assertRaises(SandboxError) as ctx:
            sbx_check_sandbox_codex(expected_version="0.149.1")
        self.assertIn("flag di disabilitazione memoria non sono supportati", str(ctx.exception))

    @patch("benchmark_core.docker_sandbox_runner._sbx_rm", return_value=(True, None))
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_check_sandbox_codex_memory_feature_active_raises(self, _which, mock_run, _rm):
        mock_run.side_effect = [
            _proc(returncode=0, stdout="Created sandbox sbx-probe"),
            _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
            _proc(returncode=0, stdout="memories  stable  true\nhooks  stable  true\n"),  # feature still true!
        ]
        with self.assertRaises(SandboxError) as ctx:
            sbx_check_sandbox_codex(expected_version="0.149.1")
        self.assertIn("feature memoria non risulta disabilitata", str(ctx.exception))


# ---------------------------------------------------------------------------
# Test: sbx_check_auth (OAuth gestito da sbx)
# ---------------------------------------------------------------------------

class TestCheckAuth(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_auth_secret_json_openai(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=0), # docker login status
            _proc(returncode=0, stdout=json.dumps([{"name": "openai", "type": "oauth"}])), # sbx secret ls --json
        ]
        sbx_check_auth()

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_auth_secret_plain_openai(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=0), # docker login status
            _proc(returncode=1), # json fail
            _proc(returncode=0, stdout="openai  secret  configured"), # plain
        ]
        sbx_check_auth()

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_auth_missing_raises(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=0), # docker login
            _proc(returncode=0, stdout="[]"), # empty json
            _proc(returncode=0, stdout="No secrets"), # plain
        ]
        with self.assertRaises(SandboxAuthError):
            sbx_check_auth()


# ---------------------------------------------------------------------------
# Test: sbx_check_network_policy
# ---------------------------------------------------------------------------

class TestNetworkPolicy(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_network_policy_ok(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=0, stdout=json.dumps({"allowed": True})),  # api.openai.com allowed
            _proc(returncode=0, stdout=json.dumps({"allowed": True})),  # chatgpt.com allowed
            _proc(returncode=1, stdout=json.dumps({"allowed": False})), # unauthorized-domain denied
            _proc(returncode=1, stdout=json.dumps({"allowed": False})), # google.com denied
        ]
        from benchmark_core.docker_sandbox_runner import sbx_check_network_policy
        sbx_check_network_policy("test-sbx")

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_network_policy_blocks_model_raises(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=1, stdout=json.dumps({"allowed": False}), stderr="Denied"), # api.openai.com blocked
        ]
        from benchmark_core.docker_sandbox_runner import sbx_check_network_policy
        with self.assertRaises(SandboxError) as ctx:
            sbx_check_network_policy("test-sbx")
        self.assertIn("connessione necessaria a api.openai.com:443 negata", str(ctx.exception))

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_network_policy_allows_unauthorized_raises(self, _which, mock_run):
        mock_run.side_effect = [
            _proc(returncode=0, stdout=json.dumps({"allowed": True})), # api.openai.com allowed
            _proc(returncode=0, stdout=json.dumps({"allowed": True})), # chatgpt.com allowed
            _proc(returncode=0, stdout=json.dumps({"allowed": True})), # unauthorized-domain unexpectedly allowed
        ]
        from benchmark_core.docker_sandbox_runner import sbx_check_network_policy
        with self.assertRaises(SandboxError) as ctx:
            sbx_check_network_policy("test-sbx")
        self.assertIn("connessione verso destinazione non autorizzata", str(ctx.exception))


# ---------------------------------------------------------------------------
# Test: _unique_sandbox_name
# ---------------------------------------------------------------------------

class TestUniqueSandboxName(unittest.TestCase):
    def test_format(self):
        name = _unique_sandbox_name("lab00_five_router", 1)
        self.assertTrue(name.startswith("kathara-"))
        parts = name.split("-")
        self.assertEqual(parts[0], "kathara")
        self.assertEqual(len(parts[-1]), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in parts[-1]))

    def test_uniqueness(self):
        names = {_unique_sandbox_name("lab", 1) for _ in range(10)}
        self.assertEqual(len(names), 10)


# ---------------------------------------------------------------------------
# Test: _sbx_rm (con retry)
# ---------------------------------------------------------------------------

class TestSbxRm(unittest.TestCase):
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_success_first_try(self, _which, mock_run):
        mock_run.return_value = _proc(returncode=0)
        ok, err = _sbx_rm("my-sandbox")
        self.assertTrue(ok)
        self.assertIsNone(err)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_retry_succeeds_on_second_try(self, _which, mock_run, _sleep):
        mock_run.side_effect = [
            _proc(returncode=1, stderr="busy"),
            _proc(returncode=0),
        ]
        ok, err = _sbx_rm("retry-sandbox")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(mock_run.call_count, 2)

    @patch("benchmark_core.docker_sandbox_runner.time.sleep")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_failure_after_retries(self, _which, mock_run, _sleep):
        mock_run.side_effect = [
            _proc(returncode=1, stderr="error 1"),
            _proc(returncode=1, stderr="error 2"),
        ]
        ok, err = _sbx_rm("fail-sandbox")
        self.assertFalse(ok)
        self.assertEqual(err, "error 2")
        self.assertEqual(mock_run.call_count, 2)


# ---------------------------------------------------------------------------
# Test: preflight_docker_sandbox
# ---------------------------------------------------------------------------

class TestPreflightDockerSandbox(unittest.TestCase):
    def _patch_all_ok(self):
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


# ---------------------------------------------------------------------------
# Test: run_codex_in_sandbox (Mock End-to-End con verifiche dei requisiti)
# ---------------------------------------------------------------------------

class TestRunCodexInSandbox(unittest.TestCase):
    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "lab"
        ws.mkdir()
        (ws / "lab.conf").write_text("[pc1]\n")
        return ws

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_success_lifecycle_and_flags(self, mock_run, _ver, _which, _home):
        """Verifica path assoluto, sbx create, niente sbx cp, memoria disabilitata, policy rete, versione."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"
            events_jsonl = (
                json.dumps({"item": {"type": "agent_message", "text": "Done"}}) + "\n" +
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}) + "\n"
            )

            # Chiamate attese:
            # 1) sbx create codex
            # 2) sbx ls --json (per estrazione ID reale)
            # 3) sbx exec codex --version
            # 4) sbx policy check network api.openai.com
            # 5) sbx policy check network chatgpt.com
            # 6) sbx policy check network unauthorized-domain
            # 7) sbx policy check network google.com
            # 8) sbx exec codex exec
            # 9) sbx rm --force
            mock_run.side_effect = [
                _proc(returncode=0, stdout="Created sandbox kathara-test-r001-abcd1234"),
                _proc(returncode=0, stdout=json.dumps([{"name": "kathara-test-r001-abcd1234", "id": "11112222-3333-4444-5555-666677778888"}])),
                _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),  # policy check api.openai.com
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),  # policy check chatgpt.com
                _proc(returncode=1, stdout=json.dumps({"allowed": False})), # policy check unauthorized-domain
                _proc(returncode=1, stdout=json.dumps({"allowed": False})), # policy check google.com
                _proc(returncode=0, stdout=events_jsonl),
                _proc(returncode=0), # rm
            ]

            result = run_codex_in_sandbox(
                prompt="Configura il lab.",
                workspace=ws,
                logs=logs,
                timeout=300,
                model="gpt-5.6-terra",
                reasoning_effort="low",
                variant="aut",
                sandbox_name="kathara-test-r001-abcd1234",
                codex_host_version="0.157.1",
            )

            self.assertTrue(result.success)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.cleanup_ok)
            self.assertEqual(result.final_message, "Done")
            self.assertEqual(result.codex_version, "0.149.1")
            self.assertEqual(result.codex_sandbox_version, "0.149.1")
            self.assertEqual(result.codex_host_version, "0.157.1")
            self.assertEqual(result.sandbox_id, "11112222-3333-4444-5555-666677778888")

            calls = [c[0][0] for c in mock_run.call_args_list]

            # Crea con `sbx create codex`
            create_cmd = calls[0]
            self.assertEqual(create_cmd[:3], ["/usr/bin/sbx", "create", "codex"])
            self.assertIn("--skills", create_cmd)
            self.assertIn("off", create_cmd)

            # Path assoluto host
            self.assertIn(str(ws.resolve()), create_cmd)
            exec_cmd = calls[7]
            self.assertIn("-C", exec_cmd)
            c_idx = exec_cmd.index("-C")
            self.assertEqual(exec_cmd[c_idx + 1], str(ws.resolve()))
            self.assertIn("-w", exec_cmd)
            w_idx = exec_cmd.index("-w")
            self.assertEqual(exec_cmd[w_idx + 1], str(ws.resolve()))
            self.assertNotIn("/workspace", exec_cmd)

            # Memoria Codex disabilitata
            self.assertIn("--disable", exec_cmd)
            dis_idx = exec_cmd.index("--disable")
            self.assertEqual(exec_cmd[dis_idx + 1], "memories")
            self.assertIn("memories=false", " ".join(exec_cmd))
            self.assertIn("memories.use_memories=false", " ".join(exec_cmd))

            # Nessun sbx cp
            cp_calls = [c for c in calls if "cp" in c]
            self.assertEqual(len(cp_calls), 0)

            # Rm chiamato con --force
            rm_cmd = calls[-1]
            self.assertIn("rm", rm_cmd)
            self.assertIn("--force", rm_cmd)

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_failure_blocks_run(self, mock_run, _ver, _which, _home):
        """Se il cleanup fallisce, solleva SandboxCleanupError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"
            events_jsonl = json.dumps({"item": {"type": "agent_message", "text": "OK"}}) + "\n"

            # 1: create ok, 2: ls ok, 3: ver ok, 4-7: policy ok, 8: exec ok, 9: rm fallisce (retry 1), 10: rm fallisce (retry 2)
            mock_run.side_effect = [
                _proc(returncode=0, stdout="Created sandbox test-rm-fail"),
                _proc(returncode=0, stdout=json.dumps([{"name": "test-rm-fail", "id": "uuid-rm-fail"}])),
                _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=0, stdout=events_jsonl),
                _proc(returncode=1, stderr="container locked"),
                _proc(returncode=1, stderr="container locked"),
            ]

            with self.assertRaises(SandboxCleanupError) as ctx:
                run_codex_in_sandbox(
                    prompt="test",
                    workspace=ws,
                    logs=logs,
                    timeout=300,
                    model=None,
                    reasoning_effort=None,
                    variant="aut",
                    sandbox_name="test-rm-fail",
                    codex_host_version="0.157.1",
                )
            self.assertIn("Cleanup del sandbox test-rm-fail fallito", str(ctx.exception))

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_executed_on_codex_failure(self, mock_run, _ver, _which, _home):
        """Il cleanup viene tentato anche se Codex fallisce e i log vengono registrati."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"

            mock_run.side_effect = [
                _proc(returncode=0, stdout="Created sandbox fail-run"),
                _proc(returncode=0, stdout=json.dumps([{"name": "fail-run", "id": "uuid-fail-run"}])),
                _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stderr="codex internal error"),
                _proc(returncode=0),  # rm
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
                    sandbox_name="fail-run",
                    codex_host_version="0.157.1",
                )
            self.assertIn("fallito", str(ctx.exception))
            calls = [c[0][0] for c in mock_run.call_args_list]
            rm_calls = [c for c in calls if "rm" in c]
            self.assertEqual(len(rm_calls), 1)

            # Verifica persistenza log e metadati anche su errore
            self.assertTrue((logs / "result.json").is_file())
            self.assertTrue((logs / "sandbox_metadata.json").is_file())
            self.assertTrue((logs / "stderr.log").is_file())

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_cleanup_and_artifacts_on_partial_create_failure(self, mock_run, _ver, _which, _home):
        """Il cleanup e la registrazione di result.json/sandbox_metadata.json avvengono anche in caso di creazione parziale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"

            mock_run.side_effect = [
                _proc(returncode=1, stderr="failed to initialize kit"),
                _proc(returncode=0),  # rm in finally
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
                    sandbox_name="fail-create",
                )
            self.assertIn("Impossibile creare il sandbox", str(ctx.exception))
            calls = [c[0][0] for c in mock_run.call_args_list]
            rm_calls = [c for c in calls if "rm" in c]
            self.assertEqual(len(rm_calls), 1)

            # Verifica che result.json e sandbox_metadata.json siano stati comunque generati
            self.assertTrue((logs / "result.json").is_file())
            res = json.loads((logs / "result.json").read_text(encoding="utf-8"))
            self.assertIn("Impossibile creare il sandbox", res.get("error", ""))
            self.assertTrue((logs / "sandbox_metadata.json").is_file())
            meta = json.loads((logs / "sandbox_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(meta.get("sandbox_name"), "fail-create")


# ---------------------------------------------------------------------------
# Test: Metadati, ID reale, Metriche coerenti e Failure diagnostics
# ---------------------------------------------------------------------------

class TestDockerSandboxMetadataAndMetricsHarden(unittest.TestCase):
    """Test mirati per:
    1. Parsing reale dell'ID da sbx ls --json e rifiuto categorico di '✓ Created sandbox...'
    2. Uniformità del campo authentication = 'sbx_oauth_proxy'
    3. Distinzione netta tra codex_host_version e codex_sandbox_version
    4. Coerenza del conteggio token tra JSON, CSV, Excel e Inspect, senza duplicare reasoning
    5. Costo monetario non disponibile se non misurabile (nessun 0.0 o prezzo inventato)
    6. Generazione garantita dei log Inspect .eval anche in caso di fallimento della run
    """

    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    def test_sbx_get_sandbox_id_extracts_uuid_and_rejects_status_strings(self, _which, mock_run):
        # Caso 1: sbx ls --json restituisce array con sandbox e vero UUID
        mock_run.return_value = _proc(
            returncode=0,
            stdout=json.dumps([{"name": "my-sbx", "id": "4a73379b-d798-4b7f-b673-f66173a7d432"}]),
        )
        self.assertEqual(sbx_get_sandbox_id("my-sbx"), "4a73379b-d798-4b7f-b673-f66173a7d432")

        # Caso 2: id contiene testo di log tipo "✓ Created sandbox my-sbx" -> deve restituire None
        mock_run.return_value = _proc(
            returncode=0,
            stdout=json.dumps([{"name": "my-sbx", "id": "✓ Created sandbox my-sbx"}]),
        )
        self.assertIsNone(sbx_get_sandbox_id("my-sbx"))

        # Caso 3: sbx non trovato nell'output ls -> None
        mock_run.return_value = _proc(returncode=0, stdout="[]")
        self.assertIsNone(sbx_get_sandbox_id("my-sbx"))

        # Caso 4: sbx ls fallisce -> None
        mock_run.return_value = _proc(returncode=1, stderr="daemon error")
        self.assertIsNone(sbx_get_sandbox_id("my-sbx"))

    def test_token_coherence_and_no_reasoning_duplication(self):
        """Verifica coerenza token tra JSON, CSV, Excel e Inspect, senza duplicare reasoning."""
        events = [
            {"type": "turn.completed", "usage": {
                "input_tokens": 109156,
                "cached_input_tokens": 82688,
                "output_tokens": 4243,
                "reasoning_output_tokens": 1400,
            }}
        ]
        usage = codex_usage(events)
        # 1. Distingue totale riportato da totale calcolato
        self.assertIsNone(usage["total_reported"])
        self.assertEqual(usage["total_calculated"], 113399)
        # 2. total coerente (109156 + 4243 = 113399, MAI 113399 + 1400)
        self.assertEqual(usage["total"], 113399)
        self.assertEqual(usage["reasoning"], 1400)

        # 3. Aggregation row
        from benchmark_core.aggregation import _run_record
        metrics = {
            "timing": {"agent_seconds": 99.5, "checker_seconds": 28.5, "total_seconds": 142.0},
            "tokens": usage,
            "checker": {"passed": 132, "total": 132, "pass_rate": 1.0},
            "status": "COMPLETED",
        }
        manifest = {
            "pipeline_state": "COMPLETED",
            "checker_execution_success": True,
            "task_success": True,
            "agent": "codex",
            "model": "gpt-5.6-terra",
        }
        record = _run_record(metrics, manifest)
        self.assertEqual(record["total_tokens"], 113399)
        self.assertEqual(record["reasoning_tokens"], 1400)
        # Costo monetario non disponibile
        self.assertIsNone(record["cost"])

    def test_inspect_eval_log_on_error_and_null_cost(self):
        """Verifica che create_inspect_eval_log generi .eval su errore e lasci total_cost a None."""
        from benchmark_core.inspect_adapter import create_inspect_eval_log
        from inspect_ai.log import read_eval_log

        with tempfile.TemporaryDirectory() as tmpdir:
            logs = Path(tmpdir)
            (logs / "result.json").write_text(json.dumps({
                "returncode": 1,
                "timed_out": False,
                "duration_seconds": 12.5,
                "error": "Simulated infrastructure failure",
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "reasoning_output_tokens": 30,
                },
            }), encoding="utf-8")
            (logs / "invocation.json").write_text(json.dumps({
                "execution_backend": "docker_sandbox",
                "authentication": "sbx_oauth_proxy",
                "codex_host_version": "0.157.1",
                "codex_sandbox_version": "0.149.1",
                "sbx_version": "0.48.0",
                "model": "gpt-5.6-terra",
            }), encoding="utf-8")
            (logs / "stderr.log").write_text("Detailed failure traceback", encoding="utf-8")

            eval_path = create_inspect_eval_log(
                logs=logs,
                run_id="test_err_run",
                prompt="test prompt",
                agent="codex",
                model="gpt-5.6-terra",
            )
            self.assertIsNotNone(eval_path)
            self.assertTrue(eval_path.is_file())

            eval_log = read_eval_log(str(eval_path))
            self.assertEqual(eval_log.status, "error")
            self.assertIn("Simulated infrastructure failure", str(eval_log.error.message))

            # Verifica metadati Inspect
            meta = eval_log.eval.metadata
            self.assertEqual(meta.get("authentication"), "sbx_oauth_proxy")
            self.assertEqual(meta.get("codex_host_version"), "0.157.1")
            self.assertEqual(meta.get("codex_sandbox_version"), "0.149.1")

            # Verifica ModelUsage: totale coerente e nessun costo monetario inventato (None)
            model_usage = list(eval_log.stats.model_usage.values())[0]
            self.assertEqual(model_usage.total_tokens, 600)
            self.assertEqual(model_usage.reasoning_tokens, 30)
            self.assertIsNone(model_usage.total_cost)



# ---------------------------------------------------------------------------
# Test: Regressione affidabilità raccolta dati, sync lab, log write e cleanup
# ---------------------------------------------------------------------------

class TestReliabilityAndDiagnosticsRegression(unittest.TestCase):
    """Test di regressione mirati all'affidabilità della raccolta dati:
    1. Errori nella scrittura di file essenziali (result.json, events.jsonl, invocation.json, sandbox_metadata.json):
       - Nessun falso successo se Codex ha avuto exit code 0: solleva SandboxArtifactError
       - Preservazione degli artefatti disponibili (stderr.log, invocation.json, metadata)
       - Preservazione dell'eccezione originale se Codex era già fallito (nessuna sovrascrittura)
    2. Errori durante la sincronizzazione del laboratorio (staging_lab / rename / copytree):
       - Generazione garantita del log Inspect AI (.eval) anche su fallimento sync
       - Propagazione corretta dell'errore di sincronizzazione
       - Preservazione dell'errore AUT originale in caso di doppio errore (AUT + sync)
    3. Errori di cleanup del sandbox:
       - Tracciamento diagnostico in sandbox_metadata.json, manifest.json e metrics.json
    4. Pipeline end-to-end su fallimento:
       - Tracciamento stato AUT_FAILED, pipeline_error, conservazione diff parziale e log Inspect .eval
    """

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "lab"
        ws.mkdir()
        (ws / "lab.conf").write_text("[pc1]\n")
        return ws

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_essential_artifact_write_failure_raises_sandbox_artifact_error_and_preserves_available(
        self, mock_run, _ver, _which, _home
    ):
        """Se Codex ha exit code 0 ma fallisce la scrittura di un file essenziale (es. events.jsonl),
        non deve produrre un falso successo: solleva SandboxArtifactError e preserva gli altri file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"
            events_content = json.dumps({"item": {"type": "agent_message", "text": "OK"}}) + "\n"

            mock_run.side_effect = [
                _proc(returncode=0, stdout="Created sandbox test-artifact-fail"),
                _proc(returncode=0, stdout=json.dumps([{"name": "test-artifact-fail", "id": "uuid-art-fail"}])),
                _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=0, stdout=events_content),
                _proc(returncode=0),  # rm
            ]

            original_write_text = Path.write_text

            def fail_events_write_text(path_self, *args, **kwargs):
                if getattr(path_self, "name", "").startswith("events.jsonl"):
                    raise OSError("Simulazione disco pieno su events.jsonl")
                return original_write_text(path_self, *args, **kwargs)

            with patch.object(Path, "write_text", new=fail_events_write_text):
                with self.assertRaises(SandboxArtifactError) as ctx:
                    run_codex_in_sandbox(
                        prompt="test prompt",
                        workspace=ws,
                        logs=logs,
                        timeout=300,
                        model=None,
                        reasoning_effort=None,
                        variant="aut",
                        sandbox_name="test-artifact-fail",
                    )

            self.assertIn("events.jsonl", str(ctx.exception))
            self.assertIn("Simulazione disco pieno", str(ctx.exception))

            # Verifica preservazione degli artefatti disponibili
            self.assertTrue((logs / "stderr.log").is_file())
            self.assertTrue((logs / "prompt_sent.md").is_file())
            self.assertTrue((logs / "invocation.json").is_file())
            self.assertTrue((logs / "result.json").is_file())
            self.assertTrue((logs / "sandbox_metadata.json").is_file())

            res = json.loads((logs / "result.json").read_text(encoding="utf-8"))
            self.assertIn("events.jsonl", res.get("error", ""))

            meta = json.loads((logs / "sandbox_metadata.json").read_text(encoding="utf-8"))
            self.assertFalse(meta.get("artifacts_ok"))
            self.assertIn("events.jsonl", str(meta.get("artifact_errors")))

    @patch("benchmark_core.docker_sandbox_runner.Path.home", return_value=Path("/nonexistent_home"))
    @patch("benchmark_core.docker_sandbox_runner.shutil.which", return_value="/usr/bin/sbx")
    @patch("benchmark_core.docker_sandbox_runner.sbx_version", return_value="0.48.0")
    @patch("benchmark_core.docker_sandbox_runner.subprocess.run")
    def test_essential_artifact_write_failure_preserves_original_execution_error(
        self, mock_run, _ver, _which, _home
    ):
        """Se Codex è fallito con errore di esecuzione e contemporaneamente fallisce la scrittura
        di un log, l'eccezione originale di esecuzione NON deve essere sovrascritta."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = self._make_workspace(Path(tmpdir))
            logs = Path(tmpdir) / "logs/aut"

            mock_run.side_effect = [
                _proc(returncode=0, stdout="Created sandbox test-exec-fail"),
                _proc(returncode=0, stdout=json.dumps([{"name": "test-exec-fail", "id": "uuid-exec-fail"}])),
                _proc(returncode=0, stdout="codex-cli 0.149.1\n"),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=0, stdout=json.dumps({"allowed": True})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stdout=json.dumps({"allowed": False})),
                _proc(returncode=1, stderr="Syntax error in router configuration"),
                _proc(returncode=0),  # rm
            ]

            from benchmark_core import workspace as ws_mod
            original_write_json = ws_mod.write_json

            def fail_result_write_json(path_obj, data, *args, **kwargs):
                if Path(path_obj).name == "result.json":
                    raise OSError("Permesso negato su result.json")
                return original_write_json(path_obj, data, *args, **kwargs)

            with patch("benchmark_core.docker_sandbox_runner.write_json", side_effect=fail_result_write_json):
                with self.assertRaises(SandboxExecutionError) as ctx:
                    run_codex_in_sandbox(
                        prompt="test prompt",
                        workspace=ws,
                        logs=logs,
                        timeout=300,
                        model=None,
                        reasoning_effort=None,
                        variant="aut",
                        sandbox_name="test-exec-fail",
                    )

            # L'errore sollevato è SandboxExecutionError (l'errore originale, non SandboxArtifactError)
            self.assertIn("Syntax error in router configuration", str(ctx.exception))
            self.assertIn("persistenza artefatti fallita", str(ctx.exception))

    def test_lab_sync_failure_still_generates_inspect_eval_log_and_raises(self):
        """In inspect_runner.py, un fallimento nella sincronizzazione del laboratorio deve comunque
        generare il log nativo Inspect AI (.eval) e sollevare l'errore di sincronizzazione."""
        from benchmark_core.inspect_runner import run_aut
        from benchmark_core.config import Config
        from benchmark_core.scenario_loader import Scenario
        from inspect_ai.log import read_eval_log

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario_dir = root / "scenarios/lab_test"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("[pc1]\n")
            scenario = Scenario("lab_test", scenario_dir)

            run = root / "runs/lab_test/T1/dns_only/r001"
            (run / "lab").mkdir(parents=True)
            (run / "lab/lab.conf").write_text("[pc1]\n")
            aut_logs = run / "logs/aut"
            aut_logs.mkdir(parents=True)

            # Prepara log AUT simulati
            (aut_logs / "result.json").write_text(json.dumps({
                "returncode": 0, "timed_out": False, "duration_seconds": 5.0,
                "final_message": "Configured pc1", "usage": {"input_tokens": 100, "output_tokens": 20},
            }), encoding="utf-8")
            (aut_logs / "events.jsonl").write_text(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}) + "\n", encoding="utf-8")
            (aut_logs / "invocation.json").write_text(json.dumps({
                "model": "gpt-5.6-terra", "execution_backend": "docker_sandbox", "authentication": "sbx_oauth_proxy",
            }), encoding="utf-8")

            config = Config(root, {
                "aut": {"version": "test", "model": "gpt-5.6-terra", "reasoning_effort": "low",
                        "dns_skill": "skills/dns/SKILL.md", "creation_skill": "skills/creation/SKILL.md"},
                "docker_sandbox": {"execution_backend": "host"},
                "benchmark": {"timeout_seconds": 10},
            })

            real_copytree = shutil.copytree

            def fail_sync_copytree(src, dst, *args, **kwargs):
                if str(dst).endswith("lab.sync-tmp"):
                    raise OSError("Errore I/O durante copia sync laboratorio")
                return real_copytree(src, dst, *args, **kwargs)

            with patch("benchmark_core.inspect_runner.run_codex"), \
                 patch("benchmark_core.inspect_runner.prepare_skill_workspace"), \
                 patch("benchmark_core.inspect_runner.shutil.copytree", side_effect=fail_sync_copytree):
                with self.assertRaises(OSError) as ctx:
                    run_aut(
                        config=config,
                        scenario=scenario,
                        run=run,
                        agent="codex",
                        original_prompt="Configura pc1",
                        skill_mode="dns_only",
                        run_id="lab_test__T1__dns_only__r001",
                    )

            self.assertIn("Errore I/O durante copia sync laboratorio", str(ctx.exception))

            # Verifica che il log Inspect .eval sia stato COMUNQUE generato nonostante l'errore di sync!
            eval_path = aut_logs / "lab_test__T1__dns_only__r001.eval"
            self.assertTrue(eval_path.is_file(), "Il log .eval di Inspect AI deve essere presente anche se la sincronizzazione fallisce!")

            eval_log = read_eval_log(str(eval_path))
            self.assertIsNotNone(eval_log)
            self.assertEqual(eval_log.eval.run_id, "lab_test__T1__dns_only__r001")

    def test_aut_failure_and_sync_failure_preserves_aut_error_and_generates_eval(self):
        """Se sia l'AUT che la sincronizzazione falliscono, l'eccezione dell'AUT deve essere
        preservata (non sovrascritta dal sync) e il log .eval deve essere generato."""
        from benchmark_core.inspect_runner import run_aut
        from benchmark_core.config import Config
        from benchmark_core.scenario_loader import Scenario

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario_dir = root / "scenarios/lab_test"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("[pc1]\n")
            scenario = Scenario("lab_test", scenario_dir)

            run = root / "runs/lab_test/T1/dns_only/r001"
            (run / "lab").mkdir(parents=True)
            (run / "lab/lab.conf").write_text("[pc1]\n")
            aut_logs = run / "logs/aut"
            aut_logs.mkdir(parents=True)

            config = Config(root, {
                "aut": {"version": "test", "model": "gpt-5.6-terra", "reasoning_effort": "low",
                        "dns_skill": "skills/dns/SKILL.md", "creation_skill": "skills/creation/SKILL.md"},
                "docker_sandbox": {"execution_backend": "host"},
                "benchmark": {"timeout_seconds": 10},
            })

            real_copytree = shutil.copytree

            def fail_sync_copytree(src, dst, *args, **kwargs):
                if str(dst).endswith("lab.sync-tmp"):
                    raise OSError("Errore secondario di sincronizzazione")
                return real_copytree(src, dst, *args, **kwargs)

            with patch("benchmark_core.inspect_runner.run_codex", side_effect=SandboxExecutionError("Errore primario AUT")), \
                 patch("benchmark_core.inspect_runner.prepare_skill_workspace"), \
                 patch("benchmark_core.inspect_runner.shutil.copytree", side_effect=fail_sync_copytree):
                with self.assertRaises(SandboxExecutionError) as ctx:
                    run_aut(
                        config=config,
                        scenario=scenario,
                        run=run,
                        agent="codex",
                        original_prompt="Configura pc1",
                        skill_mode="dns_only",
                        run_id="lab_double_fail__r001",
                    )

            # L'errore primario dell'AUT non è stato mascherato
            self.assertIn("Errore primario AUT", str(ctx.exception))

            # Il log .eval è stato comunque generato
            eval_path = aut_logs / "lab_double_fail__r001.eval"
            self.assertTrue(eval_path.is_file())

    def test_cleanup_failure_diagnostics_in_manifest_and_metrics(self):
        """Verifica che il fallimento di cleanup sia tracciato nel manifest e nelle metriche."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir)
            logs = run / "logs/aut"
            logs.mkdir(parents=True)

            # Scrive metadati sandbox con cleanup fallito
            (logs / "sandbox_metadata.json").write_text(json.dumps({
                "sandbox_name": "test-cleanup-diag",
                "sandbox_id": "uuid-clean-diag",
                "sbx_version": "0.48.0",
                "codex_sandbox_version": "0.149.1",
                "execution_backend": "docker_sandbox",
                "cleanup_ok": False,
                "cleanup_error": "daemon locked container",
                "error": "CleanupError: daemon locked container",
            }), encoding="utf-8")

            (logs / "result.json").write_text(json.dumps({
                "returncode": 0, "duration_seconds": 10.0,
                "error": "CleanupError: daemon locked container",
            }), encoding="utf-8")

            manifest = {
                "scenario_id": "test_scenario", "prompt_type": "T1", "skill_mode": "dns_only",
                "run_number": 1, "run_id": "test_cleanup__r001", "agent": "codex",
                "execution_backend": "docker_sandbox", "aut_execution_success": False,
                "pipeline_state": "AUT_FAILED", "pipeline_error": "SandboxCleanupError: daemon locked container",
                "sandbox_cleanup_ok": False, "sandbox_cleanup_error": "daemon locked container",
                "sandbox_error": "CleanupError: daemon locked container",
            }

            metrics = make_metrics(run, manifest, total_seconds=15.0, checker_seconds=None, checker_outcome=None)

            self.assertEqual(metrics["status"], "AUT_FAILED")
            self.assertFalse(metrics["agent_success"])
            self.assertEqual(metrics["pipeline_error"], "SandboxCleanupError: daemon locked container")
            self.assertIsNotNone(metrics["sandbox"])
            self.assertFalse(metrics["sandbox"]["cleanup_ok"])
            self.assertEqual(metrics["sandbox"]["cleanup_error"], "daemon locked container")
            self.assertEqual(metrics["sandbox"]["error"], "CleanupError: daemon locked container")

    def test_pipeline_e2e_tracks_failures_preserves_partial_diff_and_eval_log(self):
        """Esecuzione pipeline end-to-end con fallimento AUT: verifica transizione stato ad AUT_FAILED,
        tracciamento errori in manifest/metrics, preservazione diff parziale e log Inspect .eval."""
        from benchmark_core.config import Config
        from benchmark_core.scenario_loader import Scenario
        from benchmark_core import pipeline
        from benchmark_core import skill_modes as _sm

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenario_dir = root / "scenarios/example_dns_001"
            (scenario_dir / "lab").mkdir(parents=True)
            (scenario_dir / "lab/lab.conf").write_text("[pc1]\n")
            (scenario_dir / "lab/pc1.startup").write_text("initial config\n")
            (root / "prompt/example_dns_001").mkdir(parents=True, exist_ok=True)
            (root / "prompt/example_dns_001/T1.md").write_text("Configure pc1")
            scenario = Scenario("example_dns_001", scenario_dir)

            for rel, content in [
                ("skills/dns/SKILL.md", "---\nname: kathara-dns\ndescription: DNS skill\n---\n# DNS\n"),
                ("skills/creation/SKILL.md", "---\nname: kathara-creation\ndescription: Creation skill\n---\n# Creation\n"),
                ("scenarios/example_dns_001/correction.yaml", "canonical correction"),
            ]:
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)

            config = Config(root, {
                "aut": {"version": "test", "model": "codex-default", "reasoning_effort": "medium",
                        "dns_skill": "skills/dns/SKILL.md", "creation_skill": "skills/creation/SKILL.md"},
                "sandbox": {"image": "fixture"},
                "benchmark": {"timeout_seconds": 10},
            })

            def failing_run_aut(cfg, scn, run_dir, agent, prompt_text, skill_mode=None, run_id=None):
                aut_logs = run_dir / "logs/aut"
                aut_logs.mkdir(parents=True, exist_ok=True)
                # Simula parziale modifica del lab prima del fallimento
                (run_dir / "lab/pc1.startup").write_text("partial modified config\n")
                (aut_logs / "prompt_sent.md").write_text(prompt_text, encoding="utf-8")
                (aut_logs / "result.json").write_text(json.dumps({
                    "returncode": 1, "timed_out": False, "duration_seconds": 3.0,
                    "error": "Codex crashed during execution",
                }), encoding="utf-8")
                (aut_logs / f"{run_id}.eval").write_text("eval log content", encoding="utf-8")
                raise SandboxExecutionError("Codex in Docker Sandbox fallito (exit 1): crash")

            with patch.object(pipeline, "component_versions", return_value={}), \
                 patch.object(pipeline, "run_aut", side_effect=failing_run_aut), \
                 patch.object(pipeline, "read_correction", return_value=(b"canonical correction", "sha")), \
                 patch.object(pipeline, "validate_correction", return_value="sha"), \
                 patch.object(_sm, "validate_mode_sources", side_effect=lambda cfg, m: _sm.mode_details(m)):
                run_result = pipeline.run_one(config, scenario, "codex", "T1", "dns_only")

            # Verifica stato finale della pipeline
            manifest = json.loads((run_result / "manifest.json").read_text(encoding="utf-8"))
            metrics = json.loads((run_result / "evaluation/metrics.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["pipeline_state"], "AUT_FAILED")
            self.assertFalse(manifest["aut_execution_success"])
            self.assertIsNone(manifest["task_success"])
            self.assertIn("SandboxExecutionError", manifest["pipeline_error"])
            self.assertEqual(manifest["state_history"][-1]["state"], "AUT_FAILED")

            self.assertEqual(metrics["status"], "AUT_FAILED")
            self.assertFalse(metrics["agent_success"])
            self.assertIn("SandboxExecutionError", metrics["pipeline_error"])

            # Verifica preservazione file di errore e diff parziale
            self.assertTrue((run_result / "logs/pipeline_error.log").is_file())
            self.assertTrue((run_result / "logs/diff.json").is_file())
            diff = json.loads((run_result / "logs/diff.json").read_text(encoding="utf-8"))
            # Il file pc1.startup è stato modificato prima del crash: il diff parziale deve registrarlo!
            self.assertTrue(len(diff.get("modified", [])) > 0 or len(diff.get("added", [])) > 0)

            # Verifica presenza del log Inspect
            inspect_eval = run_result / f"logs/aut/{manifest['run_id']}.eval"
            self.assertTrue(inspect_eval.is_file(), "Il log Inspect .eval deve essere preservato!")


# ---------------------------------------------------------------------------
# Test: Test reale ciclo di vita sbx con shell agent (ZERO token LLM)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    shutil.which("sbx") and shutil.which("docker"),
    "sbx o docker non disponibili sul sistema",
)
class TestDockerSandboxRealShellLifecycle(unittest.TestCase):
    """Test di integrazione reale sull'host Mac senza uso di token LLM.

    Verifica con l'agente built-in `shell`:
    - Creazione sandbox reale con workspace montato
    - Modifica di un file nel percorso reale dall'interno del sandbox
    - Presenza immediata della modifica sul filesystem host (bind mount diretto)
    - Cleanup completo con eliminazione del sandbox
    """

    def test_real_shell_sandbox_bind_mount_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="sbx-test-real-ws-") as tmpdir:
            ws = Path(tmpdir) / "lab"
            ws.mkdir()
            host_probe_file = ws / "initial.txt"
            host_probe_file.write_text("created_on_host\n", encoding="utf-8")

            sandbox_name = f"test-real-shell-{uuid.uuid4().hex[:8]}"
            exe = sbx_executable()

            # 1. Crea sandbox reale
            create_cmd = [
                exe, "create", "shell",
                str(ws.resolve()),
                "--name", sandbox_name,
            ]
            create_res = subprocess.run(create_cmd, capture_output=True, text=True, timeout=60)
            self.assertEqual(
                create_res.returncode, 0,
                f"Creazione sandbox reale fallita:\n{create_res.stderr}"
            )

            try:
                # 2. Modifica il file e ne crea uno nuovo dal sandbox tramite path host
                inside_file = ws.resolve() / "from_sandbox.txt"
                exec_cmd = [
                    exe, "exec",
                    "-w", str(ws.resolve()),
                    sandbox_name,
                    "touch", str(inside_file),
                ]
                exec_res = subprocess.run(exec_cmd, capture_output=True, text=True, timeout=30)
                self.assertEqual(exec_res.returncode, 0, f"sbx exec fallito:\n{exec_res.stderr}")

                # 3. Verifica bind mount diretto: il file deve esistere SUBITO sull'host
                self.assertTrue(inside_file.is_file(), "Il file creato nel sandbox non esiste sull'host!")

            finally:
                # 4. Cleanup reale
                ok, err = _sbx_rm(sandbox_name)
                self.assertTrue(ok, f"Eliminazione sandbox reale fallita: {err}")

            # Verifica che il sandbox sia effettivamente rimosso
            ls_res = subprocess.run([exe, "ls"], capture_output=True, text=True, timeout=15)
            self.assertNotIn(sandbox_name, ls_res.stdout)


if __name__ == "__main__":
    unittest.main()
