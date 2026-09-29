import unittest
import subprocess
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from benchmark_core.preflight import preflight, parse_cli_version
from benchmark_core.config import Config


class PreflightVersionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("/dummy")
        self.config_codex = Config(self.root, {
            "aut": {"agent": "codex", "version": "0.146.0"},
            "benchmark": {"timeout_seconds": 30},
        })
        self.config_antigravity = Config(self.root, {
            "aut": {"agent": "antigravity", "version": "1.2.8", "dns_skill": "skills/dns.md"},
            "benchmark": {"timeout_seconds": 30},
        })
        self.config_no_version = Config(self.root, {
            "aut": {"agent": "codex"},
            "benchmark": {"timeout_seconds": 30},
        })

    def _mock_subprocess(self, stdout, returncode=0):
        mock = MagicMock()
        mock.stdout = stdout
        mock.stderr = ""
        mock.returncode = returncode
        return mock

    def test_parse_cli_version_codex_format(self):
        self.assertEqual(parse_cli_version("codex-cli 0.146.0\n"), "0.146.0")
        self.assertEqual(parse_cli_version("codex 0.146.0"), "0.146.0")
        self.assertEqual(parse_cli_version("codex-cli v0.146.0"), "0.146.0")

    def test_parse_cli_version_agy_format(self):
        self.assertEqual(parse_cli_version("1.2.8\n"), "1.2.8")

    def test_parse_cli_version_malformed_raises(self):
        with self.assertRaises(RuntimeError):
            parse_cli_version("Codex development build")

    @patch("benchmark_core.preflight.shutil.which", return_value="/bin/codex")
    @patch("benchmark_core.preflight.subprocess.run")
    def test_codex_version_match_succeeds(self, mock_run, mock_which):
        def side_effect(command, **kwargs):
            if "--version" in command:
                return self._mock_subprocess("codex-cli 0.146.0\n")
            return self._mock_subprocess("")
        mock_run.side_effect = side_effect

        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
             patch("benchmark_core.skill_modes.validate_mode_sources"):
            # This should not raise
            preflight(self.config_codex, "codex", "no_skill", [])

    @patch("benchmark_core.preflight.shutil.which", return_value="/bin/codex")
    @patch("benchmark_core.preflight.subprocess.run")
    def test_codex_version_mismatch_raises(self, mock_run, mock_which):
        def side_effect(command, **kwargs):
            if "--version" in command:
                return self._mock_subprocess("codex-cli 0.147.0\n")
            return self._mock_subprocess("")
        mock_run.side_effect = side_effect

        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
             patch("benchmark_core.skill_modes.validate_mode_sources"):
            with self.assertRaises(RuntimeError) as ctx:
                preflight(self.config_codex, "codex", "no_skill", [])
            self.assertIn("expected 0.146.0", str(ctx.exception))
            self.assertIn("actual 0.147.0", str(ctx.exception))

    @patch("benchmark_core.preflight.shutil.which", return_value="/bin/codex")
    @patch("benchmark_core.preflight.subprocess.run")
    def test_codex_version_malformed_raises(self, mock_run, mock_which):
        def side_effect(command, **kwargs):
            if "--version" in command:
                return self._mock_subprocess("Codex development build")
            return self._mock_subprocess("")
        mock_run.side_effect = side_effect

        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
             patch("benchmark_core.skill_modes.validate_mode_sources"):
            with self.assertRaises(RuntimeError) as ctx:
                preflight(self.config_codex, "codex", "no_skill", [])
            self.assertIn("Unable to parse valid version", str(ctx.exception))

    def test_config_missing_version_raises(self):
        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.skill_modes.ensure_no_external_skill_collisions"), \
             patch("benchmark_core.skill_modes.validate_mode_sources"):
            with self.assertRaises(RuntimeError) as ctx:
                preflight(self.config_no_version, "codex", "no_skill", [])
            self.assertIn("aut.version is missing", str(ctx.exception))

    @patch("benchmark_core.preflight.shutil.which", return_value="/bin/agy")
    @patch("benchmark_core.preflight.subprocess.run")
    def test_antigravity_version_match_succeeds(self, mock_run, mock_which):
        def side_effect(command, **kwargs):
            if "--version" in command:
                return self._mock_subprocess("1.2.8\n")
            return self._mock_subprocess("")
        mock_run.side_effect = side_effect

        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.config.verify_skills"):
            preflight(self.config_antigravity, "antigravity", "dns_only", [])

    @patch("benchmark_core.preflight.shutil.which", return_value="/bin/agy")
    @patch("benchmark_core.preflight.subprocess.run")
    def test_antigravity_version_mismatch_raises(self, mock_run, mock_which):
        def side_effect(command, **kwargs):
            if "--version" in command:
                return self._mock_subprocess("1.2.9\n")
            return self._mock_subprocess("")
        mock_run.side_effect = side_effect

        with patch("benchmark_core.preflight.validate_correction"), \
             patch("benchmark_core.preflight.validate_agent"), \
             patch("benchmark_core.config.verify_skills"):
            with self.assertRaises(RuntimeError) as ctx:
                preflight(self.config_antigravity, "antigravity", "dns_only", [])
            self.assertIn("expected 1.2.8", str(ctx.exception))
            self.assertIn("actual 1.2.9", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
