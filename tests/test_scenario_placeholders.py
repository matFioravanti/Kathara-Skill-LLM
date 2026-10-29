from pathlib import Path

import pytest

from benchmark_core.scenario_loader import discover_scenarios


def _placeholder(root: Path, name: str) -> Path:
    scenario = root / name
    for leaf in (scenario / "lab", scenario / "tasks/aurora/small"):
        leaf.mkdir(parents=True)
        (leaf / ".gitkeep").touch()
    return scenario


def test_placeholder_ignored_beside_complete_lab(tmp_path):
    _placeholder(tmp_path, "pending")
    complete = _placeholder(tmp_path, "ready")
    (complete / "lab/lab.conf").write_text('pc1[0]="net1"\n')
    found = discover_scenarios(tmp_path)
    assert list(found) == ["ready"]
    assert found["ready"].lab == (complete / "lab").resolve()


@pytest.mark.parametrize("relative", ["lab/pc1.startup", "tasks/aurora/small/correction.yaml"])
def test_real_file_without_lab_conf_is_error(tmp_path, relative):
    scenario = _placeholder(tmp_path, "partial")
    (scenario / relative).write_text("content\n")
    with pytest.raises(ValueError, match="lab.conf"):
        discover_scenarios(tmp_path)


def test_missing_lab_directory_is_error(tmp_path):
    (tmp_path / "partial").mkdir()
    with pytest.raises(ValueError, match="lab.conf"):
        discover_scenarios(tmp_path)


def test_symlink_is_not_treated_as_placeholder(tmp_path):
    scenario = _placeholder(tmp_path, "partial")
    (scenario / "lab/link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="lab.conf"):
        discover_scenarios(tmp_path)
