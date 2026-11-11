#!/usr/bin/env python3
"""Recover a reviewable metrics candidate without editing the original run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.checker_runner import parse_reports
from benchmark_core.run_metrics import make_metrics
from benchmark_core.workspace import tree_hash, write_json


def recover(run: Path, output: Path):
    run = run.resolve(); output = output.resolve()
    if output == ROOT or any(output.is_relative_to(ROOT / name) for name in ('runs', 'scenarios', 'prompt', 'skills')):
        raise ValueError('La destinazione deve essere esterna alle risorse sperimentali protette')
    for parent in (run, *run.parents):
        if parent.name == 'runs' and output.is_relative_to(parent):
            raise ValueError('La destinazione deve essere esterna alla directory runs')
    if output.is_relative_to(run):
        raise ValueError('La destinazione deve essere esterna alla run')
    manifest_path = run / 'manifest.json'
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError(f'Manifest non valido: {manifest_path}')
    if (manifest.get('pipeline_state') not in ('FINALIZING', 'COMPLETED')
            or manifest.get('aut_execution_success') is not True
            or manifest.get('checker_execution_success') is not True
            or type(manifest.get('task_success')) is not bool):
        raise ValueError('Non sono disponibili prove di agente e checker completati')
    outcome, _ = parse_reports(run / 'results')
    if outcome['task_success'] != manifest['task_success']:
        raise ValueError('Il risultato checker non coincide con il manifest')
    correction = run / 'evaluation/correction.yaml'
    if hashlib.sha256(correction.read_bytes()).hexdigest() != manifest.get('correction_sha256'):
        raise ValueError('Hash della correction non valido')
    if not (run/'lab').is_dir() or not (run/'input/lab').is_dir():
        raise ValueError('Laboratorio o baseline mancante')
    for path, field in ((run/'lab', 'final_lab_sha256'), (run/'input/lab', 'input_lab_sha256')):
        if not manifest.get(field) or tree_hash(path) != manifest[field]:
            raise ValueError(f'Integrità non verificabile o hash incoerente: {path}')
    candidate = {**manifest, 'pipeline_state': 'COMPLETED'}
    metrics = make_metrics(run, candidate, total_seconds=None, checker_seconds=None, checker_outcome=outcome)
    # Exclusive creation ensures that an existing report cannot be overwritten.
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'metrics.json', metrics)
    write_json(output/'recovery.json', {'source_run': str(run), 'source_manifest_sha256': hashlib.sha256(raw).hexdigest(),
                                       'status': 'candidate_only',
                                       'note': 'Tempi non ricostruibili sono null; nessun file storico è stato modificato.'})
    return output


def main():
    parser = argparse.ArgumentParser(description='Ricostruisce metriche candidate senza modificare la run')
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(f'Metriche candidate: {recover(args.run, args.output)}')
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f'Errore recupero: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
