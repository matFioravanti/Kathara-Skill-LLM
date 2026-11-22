#!/usr/bin/env python3
"""Preview or execute the frozen 450-observation Base campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark_core.workspace import tree_hash


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="start real model calls and checker evaluations")
    parser.add_argument("--task-level", choices=("small", "medium", "large"),
                        help="restrict execution to one level; default: Small, Medium, Large")
    args = parser.parse_args(argv)
    directory = ROOT / "experiments/base_full_v2"
    plan = json.loads((directory / "plan.json").read_text())
    inputs = json.loads((directory / "inputs.json").read_text())
    for relative, digest in inputs["file_sha256"].items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            parser.error(f"Frozen campaign input changed: {relative}")
    for relative, digest in inputs["tree_sha256"].items():
        if tree_hash(ROOT / relative) != digest:
            parser.error(f"Frozen baseline or Skill bundle changed: {relative}")
    mode = "execute_argv" if args.execute else "dry_run_argv"
    for item in plan["commands_in_execution_order"]:
        if args.task_level and item["level"] != args.task_level:
            continue
        print(f"{'EXECUTE' if args.execute else 'DRY-RUN'} | {item['level']} | 150 observations", flush=True)
        command = [sys.executable, *item[mode][1:]]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
