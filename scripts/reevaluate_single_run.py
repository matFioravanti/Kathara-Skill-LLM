#!/usr/bin/env python3
"""Rivaluta una sola run esistente e aggiorna il report del suo esperimento."""
import argparse
import fcntl
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.aggregation import aggregate
from benchmark_core.config import load_config
from benchmark_core.pipeline import reevaluate_run
from benchmark_core.task_catalog import historical_correction_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=ROOT / 'benchmark_dns_skill_v2.yaml')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((ROOT / 'runs').resolve()):
        parser.error('La run deve trovarsi sotto runs/')
    data = json.loads((run / 'manifest.json').read_text())
    experiment = data['experiment_id']
    if not experiment or not all(c.isalnum() or c in '_-' for c in experiment):
        parser.error('ID esperimento non valido')
    correction = historical_correction_path(ROOT, data['lab_id'], data['dns_tree_id'], data['task_level'])
    if hashlib.sha256(correction.read_bytes()).hexdigest() != data.get('correction_sha256'):
        parser.error('La correction canonica differisce da quella della run')
    print(f"Run: {run}\nIdentità: {data['execution_id']}\nCorrection: {correction}", flush=True)
    if args.dry_run:
        return
    lock_id = hashlib.sha256(f'{ROOT.resolve()}\0{experiment}'.encode()).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / 'kathara-experiment-locks' / f'{lock_id}.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Esperimento attivo: rivalutazione non avviata')
        current = json.loads((run / 'manifest.json').read_text())
        if (current.get('execution_id') != data['execution_id'] or
                hashlib.sha256(correction.read_bytes()).hexdigest() != current.get('correction_sha256')):
            raise SystemExit('Run o correction modificata: rivalutazione non avviata')
        config = load_config(args.config)
        reevaluate_run(config, run, isolated_checker=True)
        result = json.loads((run / 'manifest.json').read_text())
        print(f"Stato: {result.get('pipeline_state')}; task_success: {result.get('task_success')}", flush=True)
        aggregate(ROOT / 'runs', ROOT / 'results/general' / experiment, experiment_id=experiment)
        print('Report aggiornato.', flush=True)
        if result.get('pipeline_state') != 'COMPLETED':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
