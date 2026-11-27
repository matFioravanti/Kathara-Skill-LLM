#!/usr/bin/env python3
"""Rivaluta temporaneamente le run no_skill medium fallite nel report corrente."""
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.checker_runner import parse_reports, run_checker
from benchmark_core.config import load_config
from benchmark_core.workspace import copy_lab

config = load_config(ROOT / 'benchmark_dns_skill_v2.yaml')
correction = ROOT / 'scenarios/lab_02/tasks/base/medium/correction.yaml'
with (ROOT / 'results/general/dns_skill_pilot_v2/runs.csv').open(newline='') as f:
    rows = [r for r in csv.DictReader(f) if r['skill_mode'] == 'no_skill'
            and r['task_level'] == 'medium' and r['observation_selection'] == 'included'
            and r['task_success'] == 'False']
print(f'Run selezionate: {len(rows)}', flush=True)
with tempfile.TemporaryDirectory(prefix='no-skill-medium-check-') as tmp:
    for i, row in enumerate(rows, 1):
        original = ROOT / 'runs' / row['run_directory']
        snapshot = original / 'evaluation/correction.yaml'
        if snapshot.read_bytes() != correction.read_bytes():
            raise SystemExit(f'Correction corrente diversa dallo snapshot: {original}')
        run = Path(tmp) / f'run-{i:02d}'
        run.mkdir()
        (run / 'logs').mkdir()
        (run / 'results').mkdir()
        copy_lab(original / 'lab', run / 'lab')
        print(f"[{i}/{len(rows)}] {row['prompt_type']} rep={row['replicate']} {original.name}", flush=True)
        try:
            result = run_checker(config, run, correction, isolated=True)
            _, details = parse_reports(run / 'results')
            print(f"  Superati: {result['checks_passed']}; falliti: {result['checks_failed']}; totale: {result['checks_total']}", flush=True)
            for check in details:
                if check['Passed'] == 'False':
                    print(f"  FALLITO: {check['Test Description']} | {check['Reason']}", flush=True)
        except Exception as exc:
            print(f'  ERRORE TECNICO: {exc}', flush=True)
            for name in ('checker_stderr.log', 'checker_stdout.log'):
                log = run / 'logs' / name
                if log.exists():
                    print(log.read_text(errors='replace')[-5000:], flush=True)
            raise SystemExit(1)
