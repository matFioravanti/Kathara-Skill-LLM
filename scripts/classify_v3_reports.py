#!/usr/bin/env python3
"""Ricostruisce offline la classificazione dei report V3, conservando una copia precedente."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_existing_labs import write_reports
from benchmark_core.v3_classification import classify_checks


def rebuild(output, dry_run=False):
    manifest = json.loads((output / 'manifest.json').read_text())
    if manifest.get('status') != 'completed':
        print(f'Salto report incompleto: {output.name}')
        return
    content = (output / 'correction.yaml').read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest.get('correction_sha256'):
        raise ValueError(f'Snapshot correction incoerente: {output}')
    with (output / 'checks.csv').open(newline='') as stream:
        checks = list(csv.DictReader(stream))
    for row in checks:
        if row['passed'] not in ('True', 'False'):
            raise ValueError(f'Esito non valido in {output}')
        row['passed'] = row['passed'] == 'True'
    rows = [json.loads(p.read_text()) for p in sorted((output / 'dettagli').glob('*/evaluation.json'))]
    if len(rows) != manifest['expected_runs']:
        raise ValueError(f'Valutazioni mancanti: {output}')
    counts = {}
    for row in checks:
        counts.setdefault(row['execution_id'], [0, 0])[int(not row['passed'])] += 1
    for row in rows:
        if row['status'] == 'COMPLETED' and counts.get(row['execution_id'], [0, 0]) != [row['checks_passed'], row['checks_failed']]:
            raise ValueError(f'Conteggi dei controlli incoerenti: {output}')
    classified = classify_checks(checks, content)
    custom = [r for r in classified if r['test_description'].startswith(('Checking the exit code', 'Checking the output'))]
    missing = sum(not r['test_code'] for r in custom)
    print(f'{output.name}: {len(custom)} custom, {missing} senza codice; falliti: {sum(not r["passed"] for r in checks)}', flush=True)
    if missing:
        raise ValueError('Controlli custom senza codice: report conservato')
    if dry_run:
        return
    files = ['runs.csv', 'checks.csv', 'summary.csv', 'benchmark.xlsx', 'error_summary.csv']
    # Stage all report files before replacing any of the published ones.
    with tempfile.TemporaryDirectory(prefix='classify-v3-') as tmp:
        stage = Path(tmp)
        (stage / 'correction.yaml').write_bytes(content)
        write_reports(stage, rows, checks)
        backup = output / 'classification_history' / uuid4().hex
        backup.mkdir(parents=True)
        for name in files:
            old = output / name
            if old.is_file():
                shutil.copy2(old, backup / name)
        for name in files:
            target = output / (name + '.classification.tmp')
            shutil.copy2(stage / name, target)
            target.replace(output / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path, nargs='*')
    parser.add_argument('--all-v3', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    reports = args.reports
    if args.all_v3:
        reports += sorted(p for p in (ROOT / 'results/general').iterdir()
                          if 'v3' in p.name.lower() and (p / 'manifest.json').is_file())
    if not reports:
        parser.error('Indicare report oppure --all-v3')
    for output in dict.fromkeys(reports):
        rebuild(output.resolve(), args.dry_run)


if __name__ == '__main__':
    main()
