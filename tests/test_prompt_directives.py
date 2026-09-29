"""Regression tests: verify the full pipeline -> inspect_runner -> runner path.

Bug captured: execution_prompt() was called TWICE — once in pipeline.py and once in
inspect_runner.py — resulting in doubled $skill directives.

These tests walk through run_aut() (not mocked) and verify the exact prompt that
would reach run_codex / run_antigravity.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from benchmark_core.inspect_runner import run_aut
from benchmark_core.config import Config
from benchmark_core.scenario_loader import Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(root: Path) -> Config:
    """Creates a test Config with both skills present."""
    dns_skill = root / "skills/kathara-dns/SKILL.md"
    creation_skill = root / "skills/kathara-creation/SKILL.md"
    dns_skill.parent.mkdir(parents=True, exist_ok=True)
    creation_skill.parent.mkdir(parents=True, exist_ok=True)
    dns_skill.write_text(
        "---\nname: kathara-dns\ndescription: DNS skill\n---\n# DNS\n", encoding="utf-8"
    )
    creation_skill.write_text(
        "---\nname: kathara-creation\ndescription: Creation skill\n---\n# Creation\n",
        encoding="utf-8",
    )
    return Config(root, {
        "aut": {
            "agent": "codex",
            "version": "test",
            "model": None,
            "reasoning_effort": None,
            "dns_skill": "skills/kathara-dns/SKILL.md",
            "creation_skill": "skills/kathara-creation/SKILL.md",
        },
        "benchmark": {"timeout_seconds": 30},
        "sandbox": {"image": "test"},
    })


def _intercept_codex_prompt(config: Config, scenario: Scenario, run: Path,
                             skill_mode: str, original_prompt: str) -> str:
    """Runs run_aut(...) up to the point where run_codex would be called,
    intercepts the prompt argument, and returns it. Does NOT call Codex or Antigravity."""
    captured: dict = {}

    def fake_run_codex(*, prompt, workspace, logs, timeout, model, reasoning_effort, variant):
        captured["prompt"] = prompt
        # Write prompt_sent.md as the real runner would
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
        # Return a minimal mock result
        mock = MagicMock()
        mock.success = True
        return mock

    def fake_prepare_skill_workspace(lab, config, mode):
        pass  # Skip directory operations

    with patch("benchmark_core.inspect_runner.run_codex", side_effect=fake_run_codex), \
         patch("benchmark_core.inspect_runner.prepare_skill_workspace",
               side_effect=fake_prepare_skill_workspace), \
         patch("benchmark_core.inspect_runner.create_inspect_eval_log", return_value=None):
        run_aut(config, scenario, run, "codex", original_prompt, skill_mode=skill_mode)

    return captured["prompt"]


def _intercept_antigravity_prompt(config: Config, scenario: Scenario, run: Path,
                                   original_prompt: str) -> str:
    """Intercepts the prompt sent to run_antigravity."""
    captured: dict = {}

    def fake_run_antigravity(*, prompt, workspace, logs, timeout, model, reasoning_effort, variant):
        captured["prompt"] = prompt
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
        mock = MagicMock()
        mock.success = True
        return mock

    with patch("benchmark_core.inspect_runner.run_antigravity",
               side_effect=fake_run_antigravity), \
         patch("benchmark_core.inspect_runner.create_inspect_eval_log", return_value=None):
        run_aut(config, scenario, run, "antigravity", original_prompt, skill_mode="dns_only")

    return captured["prompt"]


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class PromptDirectiveRegressionTest(unittest.TestCase):
    """
    Regression: verify that $skill directives appear EXACTLY once in the prompt
    reaching run_codex, regardless of what pipeline.py does upstream.

    The authoritative source of truth is inspect_runner.py; pipeline.py must
    pass the original prompt unchanged.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.config = _make_config(self.root)
        lab_dir = self.root / "scenarios/lab_001/lab"
        lab_dir.mkdir(parents=True)
        (lab_dir / "lab.conf").write_text("client[0]=h1\n")
        self.scenario = Scenario("lab_001", self.root / "scenarios/lab_001")
        self.run_root = self.root / "runs"
        self.original_prompt = "Configure the lab correctly."

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run_for_mode(self, mode: str) -> str:
        run = self.run_root / mode / "r001"
        (run / "lab").mkdir(parents=True)
        return _intercept_codex_prompt(
            self.config, self.scenario, run, mode, self.original_prompt
        )

    # --- no_skill ---

    def test_no_skill_prompt_has_no_directives(self):
        prompt = self._run_for_mode("no_skill")
        self.assertEqual(prompt.count("$kathara-creation"), 0,
                         f"$kathara-creation found in no_skill prompt:\n{prompt}")
        self.assertEqual(prompt.count("$kathara-dns"), 0,
                         f"$kathara-dns found in no_skill prompt:\n{prompt}")
        self.assertIn(self.original_prompt, prompt)

    # --- creation_only ---

    def test_creation_only_prompt_has_exactly_one_creation_directive(self):
        prompt = self._run_for_mode("creation_only")
        self.assertEqual(prompt.count("$kathara-creation"), 1,
                         f"Expected exactly 1 $kathara-creation in prompt:\n{prompt}")
        self.assertEqual(prompt.count("$kathara-dns"), 0,
                         f"Unexpected $kathara-dns in creation_only prompt:\n{prompt}")
        self.assertIn(self.original_prompt, prompt)

    # --- dns_only ---

    def test_dns_only_prompt_has_exactly_one_dns_directive(self):
        prompt = self._run_for_mode("dns_only")
        self.assertEqual(prompt.count("$kathara-dns"), 1,
                         f"Expected exactly 1 $kathara-dns in prompt:\n{prompt}")
        self.assertEqual(prompt.count("$kathara-creation"), 0,
                         f"Unexpected $kathara-creation in dns_only prompt:\n{prompt}")
        self.assertIn(self.original_prompt, prompt)

    # --- both_forced ---

    def test_both_forced_prompt_has_exactly_one_of_each_directive(self):
        prompt = self._run_for_mode("both_forced")
        self.assertEqual(prompt.count("$kathara-creation"), 1,
                         f"Expected exactly 1 $kathara-creation in prompt:\n{prompt}")
        self.assertEqual(prompt.count("$kathara-dns"), 1,
                         f"Expected exactly 1 $kathara-dns in prompt:\n{prompt}")
        self.assertIn(self.original_prompt, prompt)

    # --- auto ---

    def test_auto_prompt_has_no_directives(self):
        prompt = self._run_for_mode("auto")
        self.assertEqual(prompt.count("$kathara-creation"), 0,
                         f"Unexpected $kathara-creation in auto prompt:\n{prompt}")
        self.assertEqual(prompt.count("$kathara-dns"), 0,
                         f"Unexpected $kathara-dns in auto prompt:\n{prompt}")
        self.assertIn(self.original_prompt, prompt)

    # --- prompt_sent.md SHA verification ---

    def test_prompt_sent_sha256_matches_file_bytes(self):
        """prompt_sent_sha256 must equal sha256 of logs/aut/prompt_sent.md."""
        mode = "dns_only"
        run = self.run_root / "sha_test" / mode / "r001"
        (run / "lab").mkdir(parents=True)

        prompt = _intercept_codex_prompt(
            self.config, self.scenario, run, mode, self.original_prompt
        )
        prompt_sent_path = run / "logs/aut/prompt_sent.md"
        self.assertTrue(prompt_sent_path.is_file(),
                        "prompt_sent.md not written by runner")
        file_sha = hashlib.sha256(prompt_sent_path.read_bytes()).hexdigest()
        text_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self.assertEqual(file_sha, text_sha,
                         "sha256(prompt_sent.md) != sha256(prompt string)")

    # --- Antigravity must NOT receive $kathara-dns ---

    def test_antigravity_prompt_does_not_contain_dollar_skill_directive(self):
        """Antigravity uses its own prompt format and must NOT receive $kathara-dns."""
        run = self.run_root / "antigravity_test" / "r001"
        (run / "lab").mkdir(parents=True)

        # Config for antigravity has dns_skill but no creation_skill
        agy_config = Config(self.root, {
            "aut": {
                "agent": "antigravity",
                "version": "test",
                "model": None,
                "reasoning_effort": None,
                "dns_skill": "skills/kathara-dns/SKILL.md",
            },
            "benchmark": {"timeout_seconds": 30},
            "sandbox": {"image": "test"},
        })

        prompt = _intercept_antigravity_prompt(
            agy_config, self.scenario, run, self.original_prompt
        )
        self.assertNotIn(
            "$kathara-dns", prompt,
            f"Antigravity prompt must NOT contain $kathara-dns, but got:\n{prompt}"
        )
        self.assertIn(self.original_prompt, prompt,
                      "Antigravity prompt must include the original prompt text")


# ---------------------------------------------------------------------------
# Config validation: dns_skill / creation_skill optional globally (Bug 5)
# ---------------------------------------------------------------------------

class ConfigSkillOptionalityTest(unittest.TestCase):
    """load_config() must not require dns_skill or creation_skill globally."""

    def _minimal_yaml(self, *, include_dns=True, include_creation=True,
                      tmpdir: Path | None = None) -> Path:
        import yaml
        root = tmpdir or Path(tempfile.mkdtemp())
        (root / "scenarios").mkdir(exist_ok=True)
        data = {
            "benchmark": {"repetitions": 1, "timeout_seconds": 10,
                          "continue_on_error": True},
            "aut": {"agent": "codex", "version": "1.0"},
            "sandbox": {"image": "python:3.11"},
            "checker": {"no_cache": True, "report_type": "csv"},
            "results": {"directory": "results"},
        }
        if include_dns:
            data["aut"]["dns_skill"] = "skills/dns/SKILL.md"
        if include_creation:
            data["aut"]["creation_skill"] = "skills/creation/SKILL.md"

        cfg_path = root / "benchmark.yaml"
        cfg_path.write_text(yaml.dump(data), encoding="utf-8")
        return cfg_path

    def test_load_config_succeeds_without_dns_skill(self):
        from benchmark_core.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._minimal_yaml(include_dns=False, include_creation=False,
                                     tmpdir=Path(tmp))
            # Must not raise
            config = load_config(cfg)
            self.assertEqual(config.data["aut"]["agent"], "codex")

    def test_load_config_succeeds_with_only_dns_skill(self):
        from benchmark_core.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._minimal_yaml(include_dns=True, include_creation=False,
                                     tmpdir=Path(tmp))
            config = load_config(cfg)
            self.assertIn("dns_skill", config.data["aut"])

    def test_load_config_succeeds_with_only_creation_skill(self):
        from benchmark_core.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._minimal_yaml(include_dns=False, include_creation=True,
                                     tmpdir=Path(tmp))
            config = load_config(cfg)
            self.assertIn("creation_skill", config.data["aut"])

    def test_load_config_succeeds_with_both_skills(self):
        from benchmark_core.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._minimal_yaml(include_dns=True, include_creation=True,
                                     tmpdir=Path(tmp))
            config = load_config(cfg)
            self.assertIn("dns_skill", config.data["aut"])
            self.assertIn("creation_skill", config.data["aut"])


class PipelineToRunnerTest(unittest.TestCase):
    """
    Verify the prompt that reaches run_codex when calling pipeline.run_one().
    This ensures that there is no double-application of execution_prompt()
    between pipeline.py and inspect_runner.py.
    """
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.config = _make_config(self.root)
        lab_dir = self.root / "scenarios/lab_001/lab"
        lab_dir.mkdir(parents=True)
        (lab_dir / "lab.conf").write_text("client[0]=h1\n")
        self.scenario = Scenario("lab_001", self.root / "scenarios/lab_001")
        prompt_dir = self.root / "prompt/lab_001"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "T1.md").write_text("Configure the lab.", encoding="utf-8")
        self.original_prompt = "Configure the lab."

    def tearDown(self):
        self._tmpdir.cleanup()

    def _intercept_run_one(self, mode: str) -> str:
        captured = {}
        def fake_run_codex(*, prompt, workspace, logs, timeout, model, reasoning_effort, variant):
            captured["prompt"] = prompt
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
            (logs / f"lab_001__T1__{mode}__r001.eval").write_text("{}", encoding="utf-8")
            (logs / "events.jsonl").write_text("", encoding="utf-8")
            (logs / "result.json").write_text("{}", encoding="utf-8")
            mock = MagicMock()
            mock.success = True
            return mock

        from benchmark_core import pipeline

        with patch("benchmark_core.inspect_runner.run_codex", side_effect=fake_run_codex), \
             patch("benchmark_core.inspect_runner.prepare_skill_workspace"), \
             patch("benchmark_core.pipeline.read_correction", return_value=(b"cor", "sha")), \
             patch("benchmark_core.pipeline.run_checker", return_value={"task_success": True}), \
             patch("benchmark_core.inspect_runner.create_inspect_eval_log", return_value=None):
            pipeline.run_one(self.config, self.scenario, "codex", "T1", skill_mode=mode)
        
        return captured.get("prompt", "")

    def test_pipeline_to_runner_dns_only(self):
        prompt = self._intercept_run_one("dns_only")
        self.assertEqual(prompt.count("$kathara-dns"), 1)
        self.assertEqual(prompt.count("$kathara-creation"), 0)

    def test_pipeline_to_runner_both_forced(self):
        prompt = self._intercept_run_one("both_forced")
        self.assertEqual(prompt.count("$kathara-dns"), 1)
        self.assertEqual(prompt.count("$kathara-creation"), 1)

    def test_pipeline_to_runner_antigravity_is_not_forced(self):
        captured = {}
        def fake_run_antigravity(*, prompt, workspace, logs, timeout, model, reasoning_effort, variant):
            captured["prompt"] = prompt
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "prompt_sent.md").write_text(prompt, encoding="utf-8")
            (logs / "lab_001__T1__no_skill__r001.eval").write_text("{}", encoding="utf-8")
            (logs / "events.jsonl").write_text("", encoding="utf-8")
            (logs / "result.json").write_text("{}", encoding="utf-8")
            mock = MagicMock()
            mock.success = True
            return mock

        from benchmark_core import pipeline
        
        agy_config = Config(self.root, {
            "aut": {
                "agent": "antigravity",
                "version": "test",
                "model": None,
                "reasoning_effort": None,
                "dns_skill": "skills/kathara-dns/SKILL.md",
            },
            "benchmark": {"timeout_seconds": 30},
            "sandbox": {"image": "test"},
        })
        
        with patch("benchmark_core.inspect_runner.run_antigravity", side_effect=fake_run_antigravity), \
             patch("benchmark_core.inspect_runner.prepare_skill_workspace"), \
             patch("benchmark_core.pipeline.read_correction", return_value=(b"cor", "sha")), \
             patch("benchmark_core.pipeline.run_checker", return_value={"task_success": True}), \
             patch("benchmark_core.inspect_runner.create_inspect_eval_log", return_value=None):
            run_path = pipeline.run_one(agy_config, self.scenario, "antigravity", "T1", skill_mode=None)
            
        manifest = json.loads((run_path / "manifest.json").read_text())
        self.assertEqual(manifest["skill_mode"], "no_skill")


if __name__ == "__main__":
    unittest.main()
