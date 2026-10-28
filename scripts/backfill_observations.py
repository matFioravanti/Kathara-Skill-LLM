#!/usr/bin/env python3
"""Ricostruisce le osservazioni senza riavviare agenti, laboratori o checker."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.aut_observation import observe
from benchmark_core.run_metrics import load_jsonl
from benchmark_core.aggregation import aggregate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=ROOT / 'runs')
    parser.add_argument('--output', type=Path, default=ROOT / 'results')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    updates = {}
    for path in sorted(args.runs.glob('*/*/*/r*/evaluation/metrics.json')):
        run = path.parent.parent
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
        metrics = json.loads(path.read_text(encoding='utf-8'))
        internet, skill = observe(run, manifest, load_jsonl(run / 'logs/aut/events.jsonl'))
        metrics.update(internet=internet, skill_compliance=skill)
        updates[path] = (json.dumps(metrics, ensure_ascii=False, indent=2) + '\n').encode()
    print(f'{len(updates)} run da aggiornare' + (' (anteprima: nessuna modifica)' if args.dry_run else ''))
    if args.dry_run:
        return
    # Backup before the first write; restore all affected files if aggregation fails.
    outputs = [args.output / x for x in ('runs.csv', 'checks.csv', 'summary.csv', 'benchmark.xlsx')]
    originals = {p: p.read_bytes() if p.exists() else None for p in [*updates, *outputs]}
    try:
        for path, data in updates.items():
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
                f.write(data)
                temp = f.name
            os.replace(temp, path)
        aggregate(args.runs, args.output)
    except BaseException:
        for path, data in originals.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        raise
    print(f'CSV e workbook rigenerati in {args.output}')


if __name__ == '__main__':
    main()
