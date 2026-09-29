from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark_core.codex_cli_runner import CodexExecutionError, codex_environment, run_codex
from benchmark_core.preflight import preflight


JSONL = '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"done"}}\n' \
        '{"type":"turn.completed","usage":{"input_tokens":3,"cached_input_tokens":1,"output_tokens":2,"reasoning_output_tokens":1}}\n'


class CodexCliRunnerTest(unittest.TestCase):
    def run_in_temp(self, completed: subprocess.CompletedProcess[str], *, model=None, effort=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, logs = root / "workspace", root / "logs"
            workspace.mkdir()
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="/usr/local/bin/codex"), \
                 patch("benchmark_core.codex_cli_runner.subprocess.run", return_value=completed) as execute:
                result = run_codex(prompt="configure the lab", workspace=workspace, logs=logs, timeout=17,
                                   model=model, reasoning_effort=effort, variant="with_skill")
            return result, execute.call_args, (logs / "events.jsonl").read_text()

    def test_exec_uses_host_codex_json_stdin_and_workspace(self):
        result, call, events = self.run_in_temp(subprocess.CompletedProcess([], 0, JSONL, ""), model="gpt-test", effort="low")
        command = call.args[0]
        self.assertEqual(command[0], "/usr/local/bin/codex")
        self.assertEqual(command[1], "exec")
        self.assertIn("--json", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertEqual(command[-1], "-")
        self.assertEqual(call.kwargs["input"], "configure the lab")
        self.assertEqual(str(call.kwargs["cwd"].resolve()), command[command.index("-C") + 1])
        self.assertNotIn("OPENAI_API_KEY", call.kwargs["env"])
        self.assertNotIn("CODEX_API_KEY", call.kwargs["env"])
        self.assertEqual(result.final_message, "done")
        self.assertEqual(events, JSONL)

    def test_environment_removes_only_api_key_variables(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "x", "CODEX_API_KEY": "y", "CODEX_HOME": "/kept"}, clear=False):
            environment = codex_environment()
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertEqual(environment["CODEX_HOME"], "/kept")

    def test_cli_error_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, logs = Path(temporary) / "workspace", Path(temporary) / "logs"
            workspace.mkdir()
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"), \
                 patch("benchmark_core.codex_cli_runner.subprocess.run", return_value=subprocess.CompletedProcess([], 7, "", "bad model")):
                with self.assertRaisesRegex(CodexExecutionError, "exit 7"):
                    run_codex(prompt="x", workspace=workspace, logs=logs, timeout=1, model=None, reasoning_effort=None, variant="without_skill")
            self.assertTrue((logs / "result.json").exists())

    def test_skill_variants_use_identical_codex_backend(self):
        completed = subprocess.CompletedProcess([], 0, JSONL, "")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            with patch("benchmark_core.codex_cli_runner.codex_executable", return_value="codex"), \
                 patch("benchmark_core.codex_cli_runner.subprocess.run", side_effect=lambda *a, **k: (calls.append((a, k)) or completed)):
                for variant in ("with_skill", "without_skill"):
                    workspace = root / variant
                    workspace.mkdir()
                    run_codex(prompt="same prompt", workspace=workspace, logs=root / f"{variant}-logs", timeout=10,
                              model="gpt-5.6-terra", reasoning_effort="low", variant=variant)
            first, second = calls
            self.assertEqual(first[0][0][0:7], second[0][0][0:7])
            self.assertEqual(first[1]["env"].get("OPENAI_API_KEY"), None)
            self.assertEqual(second[1]["env"].get("CODEX_API_KEY"), None)

    def test_preflight_checks_login_status(self):
        import tempfile as _tmp, pathlib as _pl
        with _tmp.TemporaryDirectory() as _t:
            class Config:
                root = _pl.Path(_t)
                data = {"aut": {}}
            calls = []
            def fake_run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "Logged in using ChatGPT", "")
            with patch("benchmark_core.preflight.shutil.which", return_value="/usr/local/bin/codex"), \
                 patch("benchmark_core.preflight.subprocess.run", side_effect=fake_run), \
                 patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
                 patch("benchmark_core.skill_modes.validate_mode_sources"):
                preflight(Config(), "codex")
            self.assertIn(["/usr/local/bin/codex", "login", "status"], calls)

    def test_preflight_reports_missing_login(self):
        import tempfile as _tmp, pathlib as _pl
        with _tmp.TemporaryDirectory() as _t:
            class Config:
                root = _pl.Path(_t)
                data = {"aut": {}}
            def fake_run(command, **kwargs):
                if command[1:] == ["login", "status"]:
                    return subprocess.CompletedProcess(command, 1, "", "not logged in")
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch("benchmark_core.preflight.shutil.which", return_value="codex"), \
                 patch("benchmark_core.preflight.subprocess.run", side_effect=fake_run), \
                 patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
                 patch("benchmark_core.skill_modes.validate_mode_sources"):
                with self.assertRaisesRegex(RuntimeError, "not authenticated"):
                    preflight(Config(), "codex")


    def _is_codex_available_and_logged_in(self) -> bool:
        import shutil
        if not shutil.which("codex"):
            return False
        try:
            result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def test_native_skill_loading_diagnostic(self):
        """Integration test: verifies real Codex CLI behavior with $skill directive.

        This test checks that no explicit SKILL.md read is observed in the events.jsonl
        trace when a skill is loaded via the native $skill directive. This is consistent
        with the 'native_loading_unobservable' status used in forced_skill_satisfaction.

        Note: this does NOT prove native loading never emits events in any future CLI
        version. It only verifies that observed_skills() finds no file-read evidence
        under current Codex CLI behavior.

        Run this test opt-in only:
            RUN_CODEX_INTEGRATION=1 python -m pytest tests/test_codex_cli_runner.py::CodexCliRunnerTest::test_native_skill_loading_diagnostic
        """
        import os as _os
        if not _os.environ.get("RUN_CODEX_INTEGRATION"):
            self.skipTest(
                "Skipped: set RUN_CODEX_INTEGRATION=1 to run live Codex integration tests."
            )

        if not self._is_codex_available_and_logged_in():
            self.skipTest("Codex CLI is not available or not logged in.")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill_dir = root / ".codex" / "skills" / "test-probe"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: test-probe\ndescription: Test skill\n---\n# Test Probe\nDo a simple addition like 2+2.",
                encoding="utf-8"
            )

            prompt = "$test-probe\nPerform the action."

            result = subprocess.run(
                ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-C", str(root), "-"],
                input=prompt, text=True, capture_output=True, timeout=30, env=os.environ,
            )
            if result.returncode != 0:
                stderr_text = result.stderr or ""
                if "Not inside a trusted directory" in stderr_text:
                    self.skipTest("Codex CLI requires trusted directory even with skip flag.")
                self.fail(
                    f"Codex CLI exited with code {result.returncode}.\n"
                    f"stderr: {stderr_text[:500]}"
                )

            import json as _json
            events = []
            for line in result.stdout.splitlines():
                try:
                    events.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass

            # If there are no events at all the output is suspicious: do not treat
            # it as evidence of unobservability – skip instead.
            if not events:
                self.skipTest(
                    "Codex returned exit 0 but produced no JSON events. "
                    "Cannot make a reliable observation."
                )

            from benchmark_core.run_metrics import observed_skills
            observed = observed_skills(events, ["test-probe"])

            # No explicit SKILL.md read observed in the trace.
            # This is consistent with native_loading_unobservable behavior.
            self.assertEqual(observed, [])

if __name__ == "__main__":
    unittest.main()
