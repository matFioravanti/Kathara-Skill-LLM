"""Metriche descrittive, indipendenti da Git e dalla correttezza."""
from difflib import SequenceMatcher
from pathlib import Path

from .workspace import manifest, write_json


def text_lines(root: Path, name: str, entries: dict):
    if name not in entries:
        return []
    if entries[name]["kind"] != "file":
        return None
    data = (root / name).read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def compute_diff(before: Path, after: Path, output: Path | None = None) -> dict:
    old = {k: v for k, v in manifest(before).items() if v["kind"] != "directory"}
    new = {k: v for k, v in manifest(after).items() if v["kind"] != "directory"}
    created, deleted = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    modified = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
    added = removed = 0
    non_text = []
    for name in created + deleted + modified:
        a, b = text_lines(before, name, old), text_lines(after, name, new)
        if a is None or b is None:
            non_text.append(name)
            continue
        for tag, i, j, m, n in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag in ("replace", "delete"):
                removed += j - i
            if tag in ("replace", "insert"):
                added += n - m
    result = dict(files_created=len(created), files_modified=len(modified), files_deleted=len(deleted),
                  files_changed=len(created) + len(modified) + len(deleted),
                  lines_added=added, lines_deleted=removed,
                  created=created, modified=modified, deleted=deleted,
                  non_text_files=non_text)
    if output:
        write_json(output, result)
    return result
