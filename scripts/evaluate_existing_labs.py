#!/usr/bin/env python3
"""Valuta lab già generati con una correction alternativa, senza mutare le run."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.checker_runner import parse_reports, run_checker
from benchmark_core.config import load_config
from benchmark_core.correction_input import read_correction, validate_correction_lab
from benchmark_core.workspace import copy_lab, tree_hash, utc_now, write_json
from benchmark_core.v3_classification import CLASS_FIELDS, classify_checks

RUN_FIELDS = ['source_run', 'observation_id', 'execution_id', 'experiment_id', 'lab_id',
              'dns_tree_id', 'task_level', 'prompt_type', 'skill_mode', 'replicate',
              'status', 'task_success', 'checks_passed', 'checks_failed', 'checks_total',
              'checker_seconds', 'error', 'detail_directory']
CHECK_FIELDS = ['execution_id', 'source_run', *CLASS_FIELDS, 'test_description', 'passed', 'reason']
ERROR_FIELDS = ['task_level', 'prompt_type', 'skill_mode', *CLASS_FIELDS, 'failed_checks', 'affected_runs']
SUMMARY_FIELDS = ['task_level', 'prompt_type', 'skill_mode', 'runs', 'evaluated',
                  'passed', 'failed', 'technical_errors', 'checks_passed', 'checks_failed']


def select_runs(source, skill_mode=None, prompt_type=None, replicate=None):
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f'Percorso run non valido: {source}')
    manifests = ([source / 'manifest.json'] if (source / 'manifest.json').is_file()
                 else sorted(source.rglob('manifest.json')))
    selected = []
    for path in manifests:
        if not path.parent.name.startswith('r') or not path.parent.name[1:].isdigit():
            continue
        if path.is_symlink() or any(p.is_symlink() for p in (path.parent, path.parent / 'lab', path.parent / 'input/lab')):
            raise ValueError(f'Link simbolico non supportato: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        if ((skill_mode and data.get('skill_mode') != skill_mode)
                or (prompt_type and data.get('prompt_type') != prompt_type)
                or (replicate is not None and data.get('replicate') != replicate)):
            continue
        run = path.parent
        if data.get('aut_execution_success') is not True or not (run / 'lab').is_dir() or not (run / 'input/lab').is_dir():
            raise ValueError(f'Run senza generazione completa o lab/baseline: {run}')
        if not data.get('execution_id'):
            raise ValueError(f'Identità execution_id mancante: {run}')
        selected.append((run, data))
    if not selected:
        raise ValueError('Nessuna run corrispondente ai filtri')
    ids = [data['execution_id'] for _, data in selected]
    if len(ids) != len(set(ids)):
        raise ValueError('Identità execution_id duplicate nella selezione')
    return selected


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_reports(output, rows, checks):
    snapshot = output / 'correction.yaml'
    if snapshot.exists():
        checks = classify_checks(checks, snapshot.read_bytes())
    groups = defaultdict(lambda: dict(runs=0, evaluated=0, passed=0, failed=0,
                                       technical_errors=0, checks_passed=0, checks_failed=0))
    for row in rows:
        group = groups[(row['task_level'], row['prompt_type'], row['skill_mode'])]
        group['runs'] += 1
        if row['status'] == 'COMPLETED':
            group['evaluated'] += 1
            group['passed' if row['task_success'] else 'failed'] += 1
            group['checks_passed'] += row['checks_passed']
            group['checks_failed'] += row['checks_failed']
        else:
            group['technical_errors'] += 1
    summary = [dict(zip(('task_level', 'prompt_type', 'skill_mode'), key), **value)
               for key, value in sorted(groups.items())]
    by_run = {r['execution_id']: r for r in rows}
    errors = {}
    for check in checks:
        if check['passed']:
            continue
        run = by_run[check['execution_id']]
        labels = {key: run.get(key) for key in ('task_level', 'prompt_type', 'skill_mode')}
        labels.update({key: check.get(key) for key in CLASS_FIELDS})
        key = tuple(labels.items())
        group = errors.setdefault(key, {**labels, 'failed_checks': 0, 'run_ids': set()})
        group['failed_checks'] += 1
        group['run_ids'].add(check['execution_id'])
    error_summary = [{k: v for k, v in group.items() if k != 'run_ids'} |
                     {'affected_runs': len(group['run_ids'])} for group in errors.values()]
    write_csv(output / 'runs.csv', RUN_FIELDS, rows)
    write_csv(output / 'checks.csv', CHECK_FIELDS, checks)
    write_csv(output / 'summary.csv', SUMMARY_FIELDS, summary)
    write_csv(output / 'error_summary.csv', ERROR_FIELDS, error_summary)
    from openpyxl import Workbook
    workbook = Workbook(write_only=True)
    for name, fields, entries in [('runs', RUN_FIELDS, rows), ('checks', CHECK_FIELDS, checks),
                                  ('summary', SUMMARY_FIELDS, summary), ('error_summary', ERROR_FIELDS, error_summary)]:
        sheet = workbook.create_sheet(name)
        sheet.append(fields)
        for row in entries:
            sheet.append([row.get(key) for key in fields])
    workbook.save(output / 'benchmark.xlsx')


def evaluate_one(index, original, data, output, config, total):
    detail = output / 'dettagli' / f'{index:04d}'
    detail.mkdir(parents=True)
    (detail / 'logs').mkdir()
    (detail / 'results').mkdir()
    before = tree_hash(original / 'lab')
    source = {'path': str(original), 'execution_id': data['execution_id'], 'lab_sha256': before}
    row = {key: data.get(key) for key in RUN_FIELDS}
    row.update(source_run=str(original), detail_directory=str(detail.relative_to(output)),
               status='CHECKER_FAILED', task_success=None, checks_passed=None, checks_failed=None,
               checks_total=None, error=None)
    print(f'[{index}/{total}] avvio {data["execution_id"]}', flush=True)
    start = time.monotonic()
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix='alternative-check-') as tmp:
            temporary = Path(tmp)
            copy_lab(original / 'lab', temporary / 'lab')
            (temporary / 'logs').symlink_to(detail / 'logs', target_is_directory=True)
            (temporary / 'results').symlink_to(detail / 'results', target_is_directory=True)
            result = run_checker(config, temporary, output / 'correction.yaml', isolated=True)
        _, details = parse_reports(detail / 'results')
        row.update(status='COMPLETED', task_success=result['task_success'],
                   checks_passed=result['checks_passed'], checks_failed=result['checks_failed'],
                   checks_total=result['checks_total'])
        checks = [{'execution_id': data['execution_id'], 'source_run': str(original),
                   'test_description': c['Test Description'], 'passed': c['Passed'] == 'True',
                   'reason': c['Reason']} for c in details]
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {exc}'
    row['checker_seconds'] = round(time.monotonic() - start, 3)
    if tree_hash(original / 'lab') != before:
        raise RuntimeError(f'Lab sorgente modificato durante la valutazione: {original}')
    write_json(detail / 'evaluation.json', row)
    return index, source, row, checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--correction', type=Path, required=True)
    parser.add_argument('--runs', type=Path, required=True, help='directory di run o contenitore di run')
    parser.add_argument('--skill-mode', choices=('no_skill', 'dns_only', 'creation_only', 'both_forced', 'auto'))
    parser.add_argument('--prompt-type', choices=('T1', 'T2', 'T3', 'T4', 'T5', 'T6'))
    parser.add_argument('--replicate', type=int)
    parser.add_argument('--config', type=Path, default=ROOT / 'benchmark_dns_skill_v2.yaml')
    parser.add_argument('--output', type=Path, required=True, help='nuova directory sotto results/general')
    parser.add_argument('--checker-workers', type=int, choices=(1, 2), default=1,
                        help='checker contemporanei (1 o 2; default 1)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.replicate is not None and args.replicate < 1:
            raise ValueError('La ripetizione deve essere positiva')
        correction = args.correction.absolute()
        content, digest = read_correction(correction)
        source = args.runs.absolute()
        selected = select_runs(source, args.skill_mode, args.prompt_type, args.replicate)
        output = args.output.absolute()
        general = (ROOT / 'results/general').resolve()
        if not output.resolve().is_relative_to(general) or output.resolve() == general:
            raise ValueError('La destinazione deve essere una nuova directory sotto results/general')
        if output.exists() or output.is_symlink():
            raise ValueError(f'Destinazione già esistente: {output}')
        for run, _ in selected:
            validate_correction_lab(correction, run / 'input/lab')
        config = load_config(args.config)
        print(f'Correction: {correction} SHA-256 {digest}\nDestinazione: {output}\nRun selezionate: {len(selected)}\nChecker contemporanei: {args.checker_workers}', flush=True)
        for run, data in selected:
            print(f"  {run} | {data['execution_id']}", flush=True)
        if args.dry_run:
            return 0
        output.mkdir(parents=True, exist_ok=False)
        (output / 'correction.yaml').write_bytes(content)
        versions = {}
        for name in ('kathara', 'kathara-lab-checker', 'PyYAML'):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        manifest = {'created_at': utc_now(), 'status': 'running', 'correction_source': str(correction),
                    'correction_sha256': digest, 'runs_source': str(source), 'config_source': str(args.config.absolute()),
                    'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
                    'checker_settings': config.data['checker'], 'timeout_seconds': config.data['benchmark']['timeout_seconds'],
                    'versions': versions, 'selection': {'skill_mode': args.skill_mode, 'prompt_type': args.prompt_type,
                    'replicate': args.replicate}, 'checker_workers': args.checker_workers,
                    'source_runs': [], 'expected_runs': len(selected)}
        write_json(output / 'manifest.json', manifest)
        results = {}
        with ThreadPoolExecutor(max_workers=args.checker_workers) as executor:
            futures = [executor.submit(evaluate_one, index, original, data, output, config, len(selected))
                       for index, (original, data) in enumerate(selected, 1)]
            for future in as_completed(futures):
                index, source_info, row, run_checks = future.result()
                results[index] = (row, run_checks)
                manifest['source_runs'].append(source_info)
                write_json(output / 'manifest.json', manifest)
                print(f"  [{index}] {row['status']} superati={row['checks_passed']} falliti={row['checks_failed']} {row['error'] or ''}", flush=True)
        rows = [results[i][0] for i in sorted(results)]
        checks = [check for i in sorted(results) for check in results[i][1]]
        write_reports(output, rows, checks)
        manifest['status'] = 'completed'
        manifest['completed_at'] = utc_now()
        write_json(output / 'manifest.json', manifest)
        print(f'Risultati: {output}', flush=True)
        return 1 if any(row['status'] != 'COMPLETED' for row in rows) else 0
    except (ValueError, OSError) as exc:
        print(f'Errore: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
