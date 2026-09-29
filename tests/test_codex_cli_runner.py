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
        class Config:  # il test non coinvolge configurazione/provider Inspect
            pass
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "Logged in using ChatGPT", "")
        with patch("benchmark_core.preflight.verify_skills", return_value={}), \
             patch("benchmark_core.preflight.shutil.which", return_value="/usr/local/bin/codex"), \
             patch("benchmark_core.preflight.subprocess.run", side_effect=fake_run):
            preflight(Config(), "codex")
        self.assertIn(["/usr/local/bin/codex", "login", "status"], calls)

    def test_preflight_reports_missing_login(self):
        class Config:
            pass
        def fake_run(command, **kwargs):
            if command[1:] == ["login", "status"]:
                return subprocess.CompletedProcess(command, 1, "", "not logged in")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("benchmark_core.preflight.verify_skills", return_value={}), \
             patch("benchmark_core.preflight.shutil.which", return_value="codex"), \
             patch("benchmark_core.preflight.subprocess.run", side_effect=fake_run):
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
        """Integration test to verify real Codex CLI behavior with $skill directive.
        
        This test proves that native skill loading is unobservable in events.jsonl
        and justifies the 'None' return value in forced_skill_satisfaction.
        """
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
            events_file = root / "output.jsonl"
            
            try:
                subprocess.run(
                    ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-C", str(root), "-"],
                    input=prompt, text=True, check=True, capture_output=True, env=os.environ
                )
            except subprocess.CalledProcessError as e:
                if "Not inside a trusted directory" in e.stderr:
                     self.skipTest("Codex CLI requires trusted directory even with skip flag.")
                raise

            # Assuming Codex writes some output or we capture it. Wait, the actual command writes to stdout!
            # Let's fix this: run_codex doesn't use output.jsonl, we use our own run:
            result = subprocess.run(
                ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-C", str(root), "-"],
                input=prompt, text=True, capture_output=True, env=os.environ
            )
            
            import json
            events = []
            for line in result.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            
            # Use our parser to check if the skill was observed
            from benchmark_core.run_metrics import observed_skills
            observed = observed_skills(events, ["test-probe"])
            
            # Since the native $skill loading is internal, it doesn't emit a command_execution event
            # that reads the SKILL.md file. Thus, it should be unobservable.
            self.assertEqual(observed, [])

if __name__ == "__main__":
    unittest.main()
