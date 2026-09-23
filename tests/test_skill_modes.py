from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark_core.skill_modes import (
    SKILL_MODES,
    ensure_no_external_skill_collisions,
    execute_skill_modes,
    expand_skill_mode,
    execution_prompt,
    prepare_skill_workspace,
    validate_mode_sources,
)
from benchmark_core.preflight import preflight


class Config:
    def __init__(self, root: Path):
        self.root = root
        self.data = {
            "aut": {
                "creation_skill": "skills/kathara-creation/SKILL.md",
                "dns_skill": "skills/dns/SKILL.md",
            }
        }

    def path(self, value: str) -> Path:
        return (self.root / value).resolve()


class SkillModesTest(unittest.TestCase):
    def make_skill(self, root: Path, slug: str, description: str, directory: str | None = None) -> Path:
        path = root / "skills" / (directory or slug) / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {slug}\ndescription: {description}\n---\nInstructions for {slug}.\n",
            encoding="utf-8",
        )
        return path

    def test_five_mode_definitions_separate_available_and_forced(self):
        self.assertEqual(SKILL_MODES["no_skill"].available_skills, ())
        self.assertEqual(SKILL_MODES["no_skill"].forced_skills, ())
        self.assertEqual(SKILL_MODES["creation_only"].available_skills, ("kathara-creation",))
        self.assertEqual(SKILL_MODES["creation_only"].forced_skills, ("kathara-creation",))
        self.assertEqual(SKILL_MODES["dns_only"].available_skills, ("kathara-dns",))
        self.assertEqual(SKILL_MODES["dns_only"].forced_skills, ("kathara-dns",))
        self.assertEqual(SKILL_MODES["both_forced"].available_skills,
                         ("kathara-creation", "kathara-dns"))
        self.assertEqual(SKILL_MODES["both_forced"].forced_skills,
                         ("kathara-creation", "kathara-dns"))
        self.assertEqual(SKILL_MODES["auto"].available_skills,
                         ("kathara-creation", "kathara-dns"))
        self.assertEqual(SKILL_MODES["auto"].forced_skills, ())

    def test_each_mode_materializes_exactly_its_available_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Config(root)
            self.make_skill(root, "kathara-creation", "Create Kathara labs.")
            self.make_skill(root, "kathara-dns", "Configure DNS in Kathara labs.", directory="dns")
            expected = {
                "no_skill": set(),
                "creation_only": {"kathara-creation"},
                "dns_only": {"kathara-dns"},
                "both_forced": {"kathara-creation", "kathara-dns"},
                "auto": {"kathara-creation", "kathara-dns"},
            }
            for mode, names in expected.items():
                workspace = root / "runs" / mode / "lab"
                workspace.mkdir(parents=True)
                stale = workspace / ".codex/skills/stale/SKILL.md"
                stale.parent.mkdir(parents=True)
                stale.write_text("stale", encoding="utf-8")
                prepare_skill_workspace(workspace, config, mode)
                copied = workspace / ".codex/skills"
                self.assertEqual({path.name for path in copied.iterdir()}, names, mode)
                self.assertEqual(
                    {path.parent.name for path in copied.glob("*/SKILL.md")}, names, mode
                )
                self.assertTrue(all((copied / name / "SKILL.md").is_file() for name in names))

    def test_only_forced_modes_prepend_the_minimal_directive(self):
        original = "Configure this existing lab.\nKeep this exact line.\n"
        self.assertEqual(execution_prompt("no_skill", original), original)
        self.assertEqual(execution_prompt("auto", original), original)
        self.assertEqual(execution_prompt("creation_only", original),
                         "Use only $kathara-creation for this task.\n\n" + original)
        self.assertEqual(execution_prompt("dns_only", original),
                         "Use only $kathara-dns for this task.\n\n" + original)
        self.assertEqual(execution_prompt("both_forced", original),
                         "Use $kathara-creation and $kathara-dns for this task.\n\n" + original)

    def test_external_user_skill_collision_blocks_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            external = root / "codex-home/skills/kathara-dns/SKILL.md"
            external.parent.mkdir(parents=True)
            external.write_text(
                "---\nname: kathara-dns\ndescription: DNS skill\n---\nInstructions.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "contaminerebbero"):
                ensure_no_external_skill_collisions(
                    project, environ={"CODEX_HOME": str(root / "codex-home")}
                )

    def test_external_plugin_skill_collision_blocks_run_by_declared_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            external = root / "codex-home/plugins/cache/example/skills/create/SKILL.md"
            external.parent.mkdir(parents=True)
            external.write_text(
                "---\nname: kathara-creation\ndescription: Creation skill\n---\nInstructions.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "contaminerebbero"):
                ensure_no_external_skill_collisions(
                    project, environ={"CODEX_HOME": str(root / "codex-home")}
                )

    def test_creation_modes_fail_preflight_until_canonical_creation_skill_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Config(root)
            self.make_skill(root, "kathara-dns", "Configure DNS in Kathara labs.", directory="dns")
            with self.assertRaisesRegex(ValueError, "kathara-creation non trovata"):
                validate_mode_sources(config, "creation_only")

    def test_execution_prompt_keeps_original_scenario_file_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            prompt_file = Path(temporary) / "prompt.txt"
            original_bytes = b"Configure this lab.\r\nKeep this exact line.\r\n"
            prompt_file.write_bytes(original_bytes)
            prompt = prompt_file.read_text(encoding="utf-8")
            execution_prompt("auto", prompt)
            self.assertEqual(prompt_file.read_bytes(), original_bytes)

    def test_all_expands_in_required_order(self):
        self.assertEqual(
            expand_skill_mode("all"),
            ("no_skill", "creation_only", "dns_only", "both_forced", "auto"),
        )

    def test_all_runs_sequentially_with_independent_workspaces_and_effective_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Config(root)
            self.make_skill(root, "kathara-creation", "Create Kathara labs.")
            self.make_skill(root, "kathara-dns", "Configure DNS in Kathara labs.", directory="dns")
            active = 0
            max_active = 0
            call_order = []
            workspaces = []

            def execute(mode, index, total):
                nonlocal active, max_active
                self.assertEqual(total, 5)
                self.assertEqual(active, 0, "la modalità precedente deve terminare prima della successiva")
                active += 1
                max_active = max(max_active, active)
                call_order.append(mode)
                workspace = root / "runs" / f"independent-{index}" / "lab"
                workspace.mkdir(parents=True)
                workspaces.append(workspace)
                prepare_skill_workspace(workspace, config, mode)
                record = {"skill_mode": mode, "workspace": workspace}
                active -= 1
                return record

            results = [result for _, _, _, result in execute_skill_modes("all", execute)]
            self.assertEqual(call_order, list(expand_skill_mode("all")))
            self.assertEqual(max_active, 1)
            self.assertEqual(len(set(workspaces)), 5)
            self.assertEqual([record["skill_mode"] for record in results], list(expand_skill_mode("all")))
            self.assertNotIn("all", [record["skill_mode"] for record in results])
            self.assertEqual(
                [{path.name for path in (workspace / ".codex/skills").iterdir()} for workspace in workspaces],
                [set(), {"kathara-creation"}, {"kathara-dns"},
                 {"kathara-creation", "kathara-dns"}, {"kathara-creation", "kathara-dns"}],
            )

    def test_all_preflight_checks_every_mode_before_any_run_can_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Config(root)
            self.make_skill(root, "kathara-dns", "Configure DNS in Kathara labs.", directory="dns")
            with patch.dict("os.environ", {"CODEX_HOME": str(root / "codex-home")}), \
                 patch("benchmark_core.preflight.verify_skills", return_value={}), \
                 patch("benchmark_core.preflight.subprocess.run") as command:
                with self.assertRaisesRegex(ValueError, "kathara-creation non trovata"):
                    preflight(config, "codex", skill_mode="all", scenario_ids=[])
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
