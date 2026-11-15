import json
from itertools import product

from benchmark_core.run_identity import describe_run, identity_fields


def test_identity_distinguishes_cells_replicates_and_attempts():
    rows = [{"experiment_id": experiment, "lab_id": lab, "dns_tree_id": "base",
             "task_level": level, "prompt_type": prompt, "skill_mode": mode,
             "replicate": replicate, "run_number": number}
            for experiment, (lab, level), prompt, mode, replicate, number in product(
                ("thesis_final", "other"), (("lab_01", "small"), ("lab_02", "medium")),
                ("T1", "T4"), ("auto", "creation_only"), (3, 4), (3, 4))]
    ids = [identity_fields(row) for row in rows]
    assert len({row["execution_id"] for row in ids}) == len(rows)
    assert len({row["observation_id"] for row in ids}) == len(rows) // 2


def test_old_manifest_is_labelled_without_renaming_or_inventing_a_replicate(tmp_path):
    run = tmp_path / "r003"
    run.mkdir()
    data = {"experiment_id": "thesis_final", "lab_id": "lab_01", "dns_tree_id": "base",
            "task_level": "small", "prompt_type": "T4", "skill_mode": "creation_only",
            "replicate": 4, "run_number": 3, "execution_id": "incorrect cached value"}
    path = run / "manifest.json"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    assert describe_run(run) == "thesis_final:lab_01:base:small:T4:creation_only:rep004:r003"
    assert path.read_bytes() == before
    data.pop("replicate")
    assert identity_fields(data)["observation_id"] is None


def test_identity_components_cannot_collide_with_separator():
    one = {"lab_id": "a:b", "prompt_type": "T1", "replicate": 1, "run_number": 1}
    two = {**one, "lab_id": "a%3Ab"}
    assert identity_fields(one)["execution_id"] != identity_fields(two)["execution_id"]
