from pathlib import Path
import tempfile
import unittest

from benchmark_core.prompts import PROMPT_TYPES, missing_prompts, resolve_prompt
from benchmark_core.scenario_loader import discover_scenarios
from benchmark_core.workspace import allocate_run_directory


class PromptSystemTest(unittest.TestCase):
    def test_scenario_without_legacy_prompt_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario = root / "scenarios/example"
            (scenario / "lab").mkdir(parents=True)
            (scenario / "lab/lab.conf").write_text("lab\n")
            (scenario / "correction.yaml").write_text("{}\n")
            self.assertIn("example", discover_scenarios(root / "scenarios"))

    def test_resolves_each_supported_type_only_under_its_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for prompt_type in ("T1", "T6"):
                path = root / "prompt/example" / f"{prompt_type}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"Prompt {prompt_type}\n")
                self.assertEqual(resolve_prompt(root, "example", prompt_type), path)
            (root / "prompt/other").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "non valido"):
                resolve_prompt(root, "example", "T7")
            with self.assertRaisesRegex(ValueError, "Missing prompt"):
                resolve_prompt(root, "other", "T1")
            self.assertEqual(PROMPT_TYPES, ("T1", "T2", "T3", "T4", "T5", "T6"))

    def test_prompt_type_is_part_of_run_path_and_numbering_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            t1, n1 = allocate_run_directory(runs, "example", "T1", "dns_only")
            t1b, n1b = allocate_run_directory(runs, "example", "T1", "dns_only")
            t2, n2 = allocate_run_directory(runs, "example", "T2", "dns_only")
            self.assertEqual([n1, n1b, n2], [1, 2, 1])
            self.assertEqual(t1.relative_to(runs).as_posix(), "example/T1/dns_only/r001")
            self.assertEqual(t1b.name, "r002")
            self.assertEqual(t2.relative_to(runs).as_posix(), "example/T2/dns_only/r001")

    def test_all_scenarios_require_their_own_prompt_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for scenario_id, body in (("A", "A prompt"), ("B", "B prompt")):
                path = root / "prompt" / scenario_id / "T1.md"
                path.parent.mkdir(parents=True)
                path.write_text(body)
            self.assertEqual(missing_prompts(root, ["A", "B"], "T1"), [])
            self.assertEqual(resolve_prompt(root, "A", "T1").read_text(), "A prompt")
            (root / "prompt/B/T1.md").unlink()
            self.assertEqual(missing_prompts(root, ["A", "B"], "T1"), ["prompt/B/T1.md"])


if __name__ == "__main__":
    unittest.main()
