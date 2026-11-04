from pathlib import Path

import pytest
import yaml

from benchmark_core.correction_input import read_correction


SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
CORRECTIONS = sorted(SCENARIOS.rglob("correction.yaml"))


def test_scenario_corrections_are_present():
    assert CORRECTIONS


@pytest.mark.parametrize("path", CORRECTIONS, ids=lambda path: str(path.relative_to(SCENARIOS)))
def test_scenario_correction_mx_targets_are_absolute(path):
    content, _ = read_correction(path)
    data = yaml.safe_load(content)
    records = data.get("test", {}).get("applications", {}).get("dns", {}).get("records", {})
    for domain, values in records.get("MX", {}).items():
        for value in values:
            parts = value.split()
            assert len(parts) == 2 and parts[0].isdigit() and parts[1].endswith("."), (
                f"{path}: MX {domain}: expected priority and absolute target, got {value!r}"
            )
