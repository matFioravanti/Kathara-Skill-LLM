"""Static DNS fixture checks and version isolation, without launching a lab."""
from hashlib import sha256
from pathlib import Path
import runpy

import pytest

from benchmark_core.config import load_config
from benchmark_core.skill_modes import mode_details, prepare_skill_workspace

ROOT = Path(__file__).resolve().parents[1]
AUDIT = runpy.run_path(str(ROOT / "skills/dns-v2/scripts/static_audit.py"))
check_dns = AUDIT["check_dns"]
check_topology = AUDIT["check_topology"]


@pytest.fixture
def observations():
    resolver = "192.0.2.20"
    ns = "ns.example."
    return {
        "servers": {
            "resolver": {"role": "resolver", "addresses": [resolver],
                         "network_ready_at": 1, "activations": [{"at": 2, "action": "start"}]},
            "authority": {"role": "authority", "addresses": ["192.0.2.30"],
                          "network_ready_at": 3, "activations": [{"at": 4, "action": "start"}]},
        },
        "clients": {"workstation": [resolver]},
        "resolver_writes": {"workstation": [["::1"], [resolver]]},
        "required_zones": [".", "example."],
        "artificial_root": True,
        "zones": {
            ".": {"soa_count": 1, "apex_ns": {"root.lab.": ["192.0.2.30"]},
                  "delegations": {"example.": {"ns": [ns], "glue": {ns: ["192.0.2.30"]}}}},
            "example.": {"soa_count": 1, "apex_ns": {ns: ["192.0.2.30"]}, "delegations": {}},
        },
    }


def test_intended_resolver_is_the_last_write(observations):
    assert check_dns(observations) == []
    observations["resolver_writes"]["workstation"].append(["127.0.0.1"])
    assert any("incorrect effective nameservers" in error for error in check_dns(observations))
    assert any("no eligible resolver" in error for error in check_dns(observations))


def test_missing_client_resolver(observations):
    del observations["resolver_writes"]["workstation"]
    assert check_dns(observations) == ["workstation: missing or incorrect effective nameservers"]


def test_authority_does_not_count_as_resolver(observations):
    observations["clients"]["workstation"] = ["192.0.2.30"]
    observations["resolver_writes"]["workstation"] = [["192.0.2.30"]]
    assert check_dns(observations) == ["workstation: no eligible resolver for 192.0.2.30"]


@pytest.mark.parametrize("activations", [
    [],
    [{"at": 2, "action": "start"}],
    [{"at": 4, "action": "start"}, {"at": 5, "action": "start"}],
])
def test_missing_early_or_duplicate_bind_start(observations, activations):
    observations["servers"]["authority"]["activations"] = activations
    assert check_dns(observations) == [
        "authority: expected one effective BIND activation after networking"
    ]


def test_single_restart_after_immutable_early_start(observations):
    observations["servers"]["authority"]["activations"] = [
        {"at": 2, "action": "start"}, {"at": 4, "action": "restart"}
    ]
    assert check_dns(observations) == []


def test_missing_zone_soa(observations):
    observations["zones"]["example."]["soa_count"] = 0
    assert check_dns(observations) == ["example.: expected one apex SOA"]


def test_missing_glue(observations):
    observations["zones"]["."]["delegations"]["example."]["glue"].clear()
    assert check_dns(observations) == [". -> example.: missing or mismatched glue for ns.example."]


def test_parent_ns_must_match_child(observations):
    observations["zones"]["."]["delegations"]["example."]["ns"] = ["different.example."]
    assert check_dns(observations) == [". -> example.: parent NS differ from child apex NS"]


def test_dns_trailer_preserves_creation_config(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    for lab in (before, after):
        lab.mkdir()
        (lab / "lab.conf").write_text('edge[0]="uplink"\n')
        (lab / "shared.startup").write_text('echo ready\n')
        (lab / "edge.startup").write_text("ip addr add 192.0.2.30/24 dev eth0\n")
    startup = after / "edge.startup"
    startup.write_text(startup.read_text() + "systemctl start named\n")
    config = after / "lab.conf"
    config.write_text(config.read_text() + 'edge[image]="kathara/bind"\n')
    assert check_topology(before, after, {"edge"}) == []
    assert check_topology(before, after, set()) == [
        "lab.conf: topology or unapproved configuration changed"
    ]
    config.write_text(config.read_text().replace("uplink", "other"))
    startup.write_text(startup.read_text().replace("192.0.2.30", "192.0.2.31"))
    (after / "shared.startup").write_text("echo changed\n")
    assert set(check_topology(before, after, {"edge"})) == {
        "lab.conf: topology or unapproved configuration changed",
        "edge.startup: original commands changed",
        "shared.startup: original commands changed",
    }


@pytest.mark.parametrize("mode", ["no_skill", "creation_only", "dns_only", "both_forced", "auto"])
def test_version_selection_stages_exactly_one_dns_bundle(tmp_path, mode):
    old = load_config(ROOT / "benchmark_dns_skill_v1.yaml")
    new = load_config(ROOT / "benchmark_dns_skill_v2.yaml")
    expected = dict(old.data)
    expected["aut"] = {**old.data["aut"], "dns_skill": "skills/dns-v2/SKILL.md"}
    assert new.data == expected

    v1 = ROOT / "skills/dns/SKILL.md"
    assert sha256(v1.read_bytes()).hexdigest() == (
        "241b4b6f0c8c72d30761bf5c237cfdc37aa23b5ef450845e7d4f23ca14f7aaf0"
    )
    for config, source in ((old, v1), (new, ROOT / "skills/dns-v2/SKILL.md")):
        details = prepare_skill_workspace(tmp_path, config, mode)
        assert details == mode_details(mode)
        root = tmp_path / ".codex/skills"
        assert {p.name for p in root.iterdir()} == set(details.available_skills)
        for name, original in (("kathara-dns", source),
                               ("kathara-creation", ROOT / "skills/kathara-creation/SKILL.md")):
            if name in details.available_skills:
                assert (root / name / "SKILL.md").read_bytes() == original.read_bytes()
        helper = root / "kathara-dns/scripts/static_audit.py"
        assert helper.exists() == (config is new and "kathara-dns" in details.available_skills)


@pytest.mark.parametrize("role,recursion,zone_types,valid", [
    ("authority", False, {".": "master"}, True),
    ("authority", False, {".": "hint"}, False),
    ("authority", True, {".": "master"}, False),
    ("resolver", True, {".": "hint"}, True),
    ("resolver", True, {".": "master"}, False),
    ("resolver", False, {".": "hint"}, False),
    ("resolver", True, {".": "hint", "example.": "master"}, False),
])
def test_root_authority_and_resolver_roles(observations, role, recursion, zone_types, valid):
    observations["servers"]["authority"].update(
        role=role, recursion=recursion, zone_types=zone_types
    )
    errors = check_dns(observations)
    assert (not errors) == valid


def test_requested_a_and_mx_records(observations):
    expected = {
        "service.example.": {"A": ["192.0.2.80"], "MX": ["10 mail.example."]}
    }
    observations["required_records"] = expected
    observations["records"] = {
        "service.example.": {"A": ["192.0.2.80"], "MX": ["10 mail.example."]}
    }
    assert check_dns(observations) == []
    del observations["records"]["service.example."]["MX"]
    assert check_dns(observations) == ["service.example.: incorrect requested MX RRset"]
    observations["records"]["service.example."]["A"] = ["192.0.2.81"]
    assert set(check_dns(observations)) == {
        "service.example.: incorrect requested A RRset",
        "service.example.: incorrect requested MX RRset",
    }


@pytest.mark.parametrize("checks,expected", [
    ([], "UNVERIFIED"),
    (["PASS"], "PASS"),
    (["PASS", "PASS"], "PASS"),
    (["PASS", "UNVERIFIED"], "UNVERIFIED"),
    (["UNVERIFIED", "FAIL"], "FAIL"),
])
def test_unavailable_tools_and_gate_precedence(checks, expected):
    assert AUDIT["gate_status"](checks) == expected


def test_audit_reads_only_explicit_input(tmp_path, observations, monkeypatch, capsys):
    import json
    import sys

    source = tmp_path / "observations.json"
    observations["gate_checks"] = {"G2": ["PASS", "UNVERIFIED"]}
    source.write_text(json.dumps(observations))
    (tmp_path / "correction.yaml").write_text("forbidden solution")
    (tmp_path / "historical-results.csv").write_text("forbidden results")
    read_text = Path.read_text
    read_paths = []

    def permitted_read(path, *args, **kwargs):
        assert path == source
        read_paths.append(path)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", permitted_read)
    monkeypatch.setattr(sys, "argv", ["static_audit.py", str(source)])
    assert AUDIT["main"]() == 0
    assert read_paths == [source]
    assert "G2: UNVERIFIED" in capsys.readouterr().out
