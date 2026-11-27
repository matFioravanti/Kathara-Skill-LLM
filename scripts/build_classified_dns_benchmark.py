#!/usr/bin/env python3
"""Build the offline, auditable original/V3 DNS benchmark dataset.

Only outputs/ is written. CSV row order is retained for provenance, never used
to infer the identity of a DNS record. SQLite and streaming XLSX bound memory.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import re
import sqlite3
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.aggregation import _run_record
from benchmark_core.check_classification import classify
from benchmark_core.classified_dns_catalog import CorrectionCatalog, digest

csv.field_size_limit(sys.maxsize)
EXPERIMENT = 'dns_skill_pilot_v2'
IDENTITY = ['execution_id', 'lab_id', 'task_level', 'prompt_id', 'skill_mode', 'repetition', 'run_id']
CHECK_FIELDS = [*IDENTITY, 'correction_version', 'evaluation_id', 'analysis_included', 'check_id',
                'definition_id', 'common_control_id', 'check_category', 'check_subcategory', 'check_type', 'error_code',
                'error_description', 'correction_comment', 'device', 'record_type', 'test_description',
                'command', 'expected_result', 'actual_result', 'passed', 'check_status', 'error_present',
                'failure_reason', 'classification_source', 'classification_status', 'classification_reason',
                'correction_path', 'correction_line', 'correction_sha256', 'source_csv', 'source_csv_row',
                'row_origin', 'definition_path', 'Test Description', 'Passed', 'Reason', 'source_extra_json']
EPR_FIELDS = [*IDENTITY, 'correction_version', 'evaluation_id', 'analysis_included', 'error_code',
              'expected_checks', 'executed_checks', 'passed_checks', 'failed_checks', 'not_executed_checks',
              'unknown_checks', 'imported_checks', 'unattributed_expected_checks', 'success_percentage',
              'failure_percentage', 'error_present']
GROUP_KEYS = ['task_level', 'prompt_id', 'skill_mode', 'correction_version', 'error_code']
GROUP_FIELDS = [*GROUP_KEYS, 'runs', 'evaluable_runs', 'runs_with_error', 'runs_without_error', 'unknown_runs',
                'error_frequency_percentage', 'executed_checks', 'passed_checks', 'failed_checks',
                'success_percentage', 'failure_percentage']
SUMMARY_KEYS = ['task_level', 'prompt_id', 'skill_mode', 'correction_version']
SUMMARY_FIELDS = [*SUMMARY_KEYS, 'runs', 'completed_runs', 'evaluated_runs', 'fully_successful_runs',
                  'run_success_percentage', 'mean_check_success_percentage', 'mean_generation_seconds',
                  'median_generation_seconds', 'mean_total_tokens', 'median_total_tokens', 'failed_checks',
                  'distinct_error_codes_observed', 'checker_technical_errors']


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        name = prefix + str(key)
        if isinstance(item, dict):
            if not item:
                result[name] = '{}'
            result.update(flatten(item, name + '.'))
        else:
            result[name] = dumps(item) if isinstance(item, (list, tuple)) else item
    return result


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def percentage(a, b):
    return 100 * a / b if b else None


def mean(values):
    numbers = [x for x in values if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return statistics.fmean(numbers) if numbers else None


def median(values):
    numbers = [x for x in values if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return statistics.median(numbers) if numbers else None


class Builder:
    def __init__(self, root, db):
        self.root, self.db = root, db
        db.execute('CREATE TABLE checks (n INTEGER PRIMARY KEY, evaluation TEXT, code TEXT, status TEXT, classified INTEGER, origin TEXT, data TEXT)')
        self.inventory = {}
        self.issues = []
        self.catalogs = {}
        self.catalog_paths = collections.defaultdict(set)
        self.run_rows = {}
        self.evaluations = []
        self.epr = []
        self.original_manifests = []
        self.stats = collections.Counter()
        self.output_rows = collections.Counter()

    def rel(self, path):
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def issue(self, kind, source, detail, severity='warning'):
        self.issues.append(dict(type=kind, source=str(source), detail=str(detail), severity=severity))

    def track(self, path):
        path = path.resolve()
        key = str(path)
        if key not in self.inventory:
            stat = path.stat()
            self.inventory[key] = dict(path=self.rel(path), size=stat.st_size, sha256=sha_file(path),
                                       mtime_ns=stat.st_mtime_ns)

    def load_json(self, path, default=None):
        try:
            self.track(path)
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            self.issue('json_missing_or_invalid', path, exc)
            return {} if default is None else default

    def catalog(self, path, expected_sha=None):
        try:
            self.track(path)
            content = path.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            if expected_sha and sha != expected_sha:
                self.issue('correction_hash_mismatch', path, f'expected={expected_sha} actual={sha}', 'error')
                return None
            if sha not in self.catalogs:
                self.catalogs[sha] = CorrectionCatalog(content)
            self.catalog_paths[sha].add(self.rel(path))
            return self.catalogs[sha]
        except (OSError, ValueError) as exc:
            self.issue('correction_unreadable', path, exc, 'error')
            return None

    def discover(self):
        root = self.root / 'runs' / EXPERIMENT
        paths = sorted(root.glob('*/*/*/*/*/r*/manifest.json'))
        self.original_manifests = paths
        report_rows = {}
        report = self.root / 'results/general' / EXPERIMENT / 'runs.csv'
        if report.is_file():
            self.track(report)
            with report.open(newline='') as stream:
                for row in csv.DictReader(stream):
                    report_rows[row.get('execution_id')] = row
        logical = collections.defaultdict(list)
        for path in paths:
            manifest = self.load_json(path)
            if manifest.get('experiment_id') != EXPERIMENT:
                self.issue('wrong_experiment', path, manifest.get('experiment_id'), 'error')
                continue
            eid = manifest.get('execution_id')
            if not eid:
                eid = ':'.join(str(manifest.get(k, '')) for k in ('experiment_id', 'lab_id', 'dns_tree_id', 'task_level', 'prompt_type', 'skill_mode', 'replicate', 'run_number'))
                self.issue('reconstructed_execution_id', path, eid)
            if eid in self.run_rows:
                self.issue('duplicate_execution_id', path, eid, 'error')
                continue
            metrics = self.load_json(path.parent / 'evaluation/metrics.json')
            row = {k: v for k, v in _run_record(metrics, manifest).items() if not k.startswith('_')}
            # Preserve every existing report column, plus the source JSON leaves.
            for k, v in report_rows.get(eid, {}).items():
                row.setdefault(k, v)
            row.update(flatten(manifest, 'manifest.'))
            row.update(flatten(metrics, 'metrics.'))
            row.update(execution_id=eid, prompt_id=manifest.get('prompt_type'), repetition=manifest.get('replicate'),
                       run_id=manifest.get('run_id'), source_run=self.rel(path.parent),
                       source_manifest=self.rel(path), source_metrics=self.rel(path.parent / 'evaluation/metrics.json'))
            row['manifest_json'] = dumps(manifest)
            row['metrics_json'] = dumps(metrics)
            self.run_rows[eid] = row
            logical_key = tuple(manifest.get(k) for k in ('lab_id', 'dns_tree_id', 'task_level', 'prompt_type', 'skill_mode', 'replicate'))
            logical[logical_key].append(eid)
            self.evaluations.append(self.make_eval(eid, manifest, path.parent / 'evaluation/correction.yaml',
                                                  path.parent / 'results', 'original', True,
                                                  data=metrics, source=path))
            for history in sorted((path.parent / 'evaluation/history').glob('revision_*/manifest.json')):
                old = self.load_json(history)
                old_metrics = self.load_json(history.parent / 'metrics.json')
                revision = old.get('evaluation_revision', history.parent.name)
                self.evaluations.append(self.make_eval(eid, old, history.parent / 'correction.yaml', history.parent / 'results',
                                                       f'original_history_{revision}', False, data=old_metrics, source=history))
        for key, eids in logical.items():
            if len(eids) > 1:
                self.issue('multiple_physical_attempts', str(key), dumps(eids))
        # Canonical files contribute documentation only; evaluation matching uses snapshots.
        for lab, level in (('lab_01', 'small'), ('lab_02', 'medium'), ('lab_03', 'large')):
            folder = self.root / 'scenarios' / lab / 'tasks/base' / level
            for name in ('correction.yaml', f'correction_{level}_custom_v3.yaml'):
                path = folder / name
                if path.exists():
                    self.catalog(path)
        self.discover_v3()
        self.stats['original_runs'] = len(self.run_rows)
        present = {(r.get('task_level'), r.get('skill_mode')) for r in self.run_rows.values()}
        for level in ('small', 'medium', 'large'):
            for mode in ('no_skill', 'creation_only', 'dns_only', 'both_forced', 'auto'):
                if (level, mode) not in present:
                    self.issue('combination_absent', f'{level}/{mode}', 'Nessuna generazione presente; non sono state create run sintetiche', 'info')

    def make_eval(self, eid, manifest, correction, results, version, included, data=None, source=None):
        return dict(execution_id=eid, correction_version=version, analysis_included=included,
                    evaluation_id=f'{eid}|{version}|{self.rel(source)}', manifest=manifest, metrics=data or {},
                    correction=correction, results=results, source=source,
                    status=manifest.get('pipeline_state', manifest.get('status')),
                    task_success=manifest.get('task_success'), correction_sha256=manifest.get('correction_sha256'))

    def discover_v3(self):
        candidates = collections.defaultdict(list)
        source_paths = {str((self.root / r['source_run']).resolve()): eid for eid, r in self.run_rows.items()}
        for folder in sorted((self.root / 'results/general').iterdir()):
            f = folder / 'manifest.json'
            if 'v3' not in folder.name.lower() or not f.is_file():
                continue
            report = self.load_json(f)
            if report.get('status') != 'completed':
                self.issue('v3_report_incomplete', folder, f"status={report.get('status')}; risultati disponibili conservati come tentativi")
            correction = folder / 'correction.yaml'
            self.catalog(correction, report.get('correction_sha256'))
            details = sorted((folder / 'dettagli').glob('*/evaluation.json'))
            for path in details:
                data = self.load_json(path)
                eid = data.get('execution_id')
                source = data.get('source_run')
                verified_eid = source_paths.get(str(Path(source).resolve())) if source else None
                if eid not in self.run_rows or (source and verified_eid != eid):
                    self.issue('v3_join_unverified', path, f'execution_id={eid} source={source}', 'error')
                    continue
                candidate = self.make_eval(eid, data, correction, path.parent / 'results', 'V3', True, data=data, source=path)
                candidate['correction_sha256'] = report.get('correction_sha256')
                candidate['report_name'] = folder.name
                candidate['report_complete'] = report.get('status') == 'completed'
                candidate['report_time'] = report.get('completed_at') or report.get('created_at', '')
                candidates[eid].append(candidate)
            for directory in sorted((folder / 'dettagli').iterdir()) if (folder / 'dettagli').exists() else []:
                if directory.is_dir() and not (directory / 'evaluation.json').exists():
                    self.issue('v3_unlinked_partial_detail', directory, 'Nessun execution_id salvato: associazione non ricostruita per posizione')
        for eid, evaluations in candidates.items():
            preferred = max(evaluations, key=lambda e: (e['report_complete'], e['status'] == 'COMPLETED', e['report_time']))
            for e in evaluations:
                if e is not preferred:
                    e['correction_version'] = 'V3_attempt_' + e['report_name']
                    e['analysis_included'] = False
                    e['evaluation_id'] += '|historical_attempt'
                    self.issue('v3_additional_attempt', e['source'], f'Preservato; escluso dai denominatori principali; selected={preferred["source"]}', 'info')
                self.evaluations.append(e)
            row = self.run_rows[eid]
            row.update({str(k) + '_v3': v for k, v in preferred['metrics'].items()})
            row['evaluation_id_v3'] = preferred['evaluation_id']
            row['correction_sha256_v3'] = preferred['correction_sha256']
            row['v3_evaluation_attempts'] = len(evaluations)
        for eid in self.run_rows:
            if eid not in candidates:
                self.issue('v3_evaluation_absent', eid, 'Nessuna rivalutazione V3 associata; celle _v3 vuote', 'info')
        self.stats['v3_evaluations'] = sum(len(v) for v in candidates.values())
        self.stats['v3_selected_evaluations'] = len(candidates)

    def base_identity(self, e):
        original = self.run_rows[e['execution_id']]
        return {k: original.get(k) for k in IDENTITY} | {k: e[k] for k in ('correction_version', 'evaluation_id', 'analysis_included')}

    def append_check(self, row):
        self.db.execute('INSERT INTO checks(evaluation,code,status,classified,origin,data) VALUES(?,?,?,?,?,?)',
                        (row['evaluation_id'], row['error_code'], row['check_status'],
                         int(row['classification_status'] == 'CLASSIFIED'), row['row_origin'], dumps(row)))
        self.stats['checks_all_rows'] += 1
        self.stats['status_' + row['check_status']] += 1
        if row['row_origin'] == 'csv':
            self.stats['imported_controls'] += 1
            version = row['correction_version']
            kind = 'original' if version == 'original' else 'v3' if version == 'V3' else 'history_or_retry'
            self.stats['imported_' + kind] += 1
            self.stats['classified_imported'] += row['classification_status'] == 'CLASSIFIED'
        if row['classification_status'] != 'CLASSIFIED':
            self.stats['unclassified_rows'] += 1

    def process_evaluation(self, e):
        issue_mark = len(self.issues)
        cat = self.catalog(e['correction'], e.get('correction_sha256'))
        defs = cat.definitions if cat else []
        expected_counts = collections.Counter(d['error_code'] for d in defs)
        description_counts = collections.Counter(d['test_description'] for d in defs)
        observed_descriptions = collections.Counter()
        observed_ids = collections.Counter()
        counts = collections.defaultdict(collections.Counter)
        details = e['results'] / 'lab/lab_result_all.csv'
        source = e['results'] / 'results.csv'
        identity = self.base_identity(e)
        raw_totals = collections.Counter()
        actual_failed = []
        if e['status'] != 'COMPLETED':
            self.issue('evaluation_incomplete_or_technical', e['source'], f"{e['status']}: {e['manifest'].get('error', e['manifest'].get('pipeline_error', ''))}")
        if details.exists():
            self.track(details)
            with details.open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                if not {'Test Description', 'Passed', 'Reason'}.issubset(reader.fieldnames or []):
                    self.issue('csv_schema_invalid', details, reader.fieldnames, 'error')
                else:
                    for n, raw in enumerate(reader, 2):
                        desc, reason = raw['Test Description'], raw['Reason'] or ''
                        status = {'True': 'PASS', 'False': 'FAIL'}.get(raw['Passed'], 'UNKNOWN')
                        if status == 'FAIL':
                            actual_failed.append(raw)
                        match, why = cat.match(desc, reason) if cat else (None, 'CORRECTION_NOT_VERIFIED')
                        observed_descriptions[desc] += 1
                        native_category, native_sub, native_rec, _ = classify(desc)
                        if match:
                            fields = dict(match)
                            observed_ids[fields['definition_id']] += 1
                        else:
                            fields = dict(error_code='UNCLASSIFIED', check_category=native_category,
                                          check_subcategory=native_sub, check_type=native_sub, record_type=native_rec or '')
                        code = fields['error_code']
                        row = identity | fields | dict(check_id=digest(f'{e["evaluation_id"]}|{self.rel(details)}|{n}'),
                            test_description=desc, actual_result=reason, failure_reason=reason if status != 'PASS' else '',
                            passed=True if status == 'PASS' else False if status == 'FAIL' else None,
                            check_status=status, error_present=1 if status == 'FAIL' else 0 if status == 'PASS' else None,
                            classification_status='CLASSIFIED' if code != 'UNCLASSIFIED' else 'UNCLASSIFIED',
                            classification_source='correction_exact_definition' if match else 'unverified',
                            classification_reason=why, correction_path=self.rel(e['correction']),
                            correction_sha256=e.get('correction_sha256'), source_csv=self.rel(details), source_csv_row=n,
                            row_origin='csv', **raw, source_extra_json=dumps(raw))
                        self.append_check(row)
                        counts[code][status] += 1
                        raw_totals[status] += 1
        else:
            self.issue('detail_csv_missing', details, f"status={e['status']}")
        if source.exists():
            self.track(source)
            with source.open(newline='') as stream:
                totals = list(csv.DictReader(stream))
            if len(totals) == 1:
                expected_total = [totals[0].get(k) for k in ('Tests Passed', 'Tests Failed', 'Tests Total Number')]
                try:
                    expected_total = list(map(int, expected_total))
                    actual = [raw_totals['PASS'], raw_totals['FAIL'], sum(raw_totals.values())]
                    if actual != expected_total:
                        self.issue('checker_summary_mismatch', source, f'CSV={actual} summary={expected_total}', 'error')
                except (ValueError, TypeError):
                    self.issue('checker_summary_unreadable', source, expected_total, 'error')
        elif e['status'] == 'COMPLETED':
            self.issue('checker_summary_missing', source, 'Valutazione COMPLETED senza riepilogo', 'error')
        for name in ('lab_result_summary.csv', 'lab_result_failed.csv'):
            auxiliary = e['results'] / 'lab' / name
            if auxiliary.exists():
                self.track(auxiliary)
                with auxiliary.open(newline='') as stream:
                    auxiliary_rows = list(csv.DictReader(stream))
                if name == 'lab_result_failed.csv' and auxiliary_rows != actual_failed:
                    self.issue('failed_csv_mismatch', auxiliary, 'Diverso dai fallimenti del CSV completo', 'error')
                if name == 'lab_result_summary.csv':
                    try:
                        values = [int(auxiliary_rows[0][k]) for k in ('Total Tests', 'Passed Tests', 'Failed')]
                        if values != [sum(raw_totals.values()), raw_totals['PASS'], raw_totals['FAIL']]:
                            self.issue('detailed_summary_mismatch', auxiliary, values, 'error')
                    except (KeyError, ValueError, IndexError):
                        self.issue('detailed_summary_invalid', auxiliary, 'Formato non riconosciuto', 'error')
        data = e['metrics']
        declared = data.get('checker') or {}
        declared_total = declared.get('total', data.get('checks_total'))
        if e['status'] == 'COMPLETED' and declared_total is not None and declared_total != sum(raw_totals.values()):
            self.issue('metrics_total_mismatch', e['source'], f'metrics={declared_total} CSV={sum(raw_totals.values())}', 'error')
        # Missing unique definitions are explicit NOT_EXECUTED; ambiguous pools
        # with observed generic rows cannot reveal which expected member is missing.
        grouped_defs = collections.defaultdict(list)
        for d in defs:
            grouped_defs[d['test_description']].append(d)
        for desc, group in grouped_defs.items():
            remaining = max(0, len(group) - observed_descriptions[desc])
            if not remaining:
                continue
            if observed_descriptions[desc] and len({d['definition_id'] for d in group}) > 1:
                self.issue('missing_check_identity_ambiguous', e['source'], f'{desc}: {remaining} previsti senza esito identificabile')
                continue
            for i, definition in enumerate(group[:remaining]):
                code = definition['error_code']
                row = identity | definition | dict(check_id=digest(f'{e["evaluation_id"]}|missing|{definition["definition_id"]}|{i}'),
                    passed=None, check_status='NOT_EXECUTED', error_present=None, actual_result=None,
                    classification_status='CLASSIFIED' if code != 'UNCLASSIFIED' else 'UNCLASSIFIED',
                    classification_source='correction_expected_definition', classification_reason='CSV privo di un risultato associabile',
                    correction_path=self.rel(e['correction']), correction_sha256=e.get('correction_sha256'),
                    source_csv='', source_csv_row=None, row_origin='expected_without_result')
                self.append_check(row)
                counts[code]['NOT_EXECUTED'] += 1
        for code in sorted(set(expected_counts) | set(counts)):
            c = counts[code]
            imported = c['PASS'] + c['FAIL'] + c['UNKNOWN']
            expected = max(expected_counts[code], imported + c['NOT_EXECUTED'])
            executed = c['PASS'] + c['FAIL']
            unknown = max(c['UNKNOWN'], expected - executed - c['NOT_EXECUTED'])
            presence = 1 if c['FAIL'] else 0 if expected and executed == expected and not unknown and not c['NOT_EXECUTED'] else None
            self.epr.append(identity | dict(error_code=code, expected_checks=expected, executed_checks=executed,
                passed_checks=c['PASS'], failed_checks=c['FAIL'], not_executed_checks=c['NOT_EXECUTED'],
                unknown_checks=unknown, imported_checks=imported,
                unattributed_expected_checks=max(0, expected - sum(c.values())),
                success_percentage=percentage(c['PASS'], executed), failure_percentage=percentage(c['FAIL'], executed),
                error_present=presence))
        e['raw_totals'] = raw_totals
        e['has_results'] = bool(raw_totals)
        missing = sum(max(0, n - observed_descriptions[desc]) for desc, n in description_counts.items())
        e['report_consistent'] = (e['status'] == 'COMPLETED' and bool(raw_totals) and cat is not None
                                  and raw_totals['UNKNOWN'] == 0 and missing == 0
                                  and not any(i['severity'] == 'error' for i in self.issues[issue_mark:]))
        e['csv_success'] = not raw_totals['FAIL'] if e['report_consistent'] else None
        if e['report_consistent'] and e['task_success'] != e['csv_success']:
            self.issue('task_success_mismatch', e['source'], f"manifest={e['task_success']} CSV={e['csv_success']}", 'error')
        self.db.commit()

    def catalog_rows(self):
        groups = {}
        for sha, cat in self.catalogs.items():
            version = 'V3' if any(d['error_code'].startswith('DNS_') for d in cat.definitions) else 'original'
            paths = self.catalog_paths[sha]
            levels = {level for level in ('small', 'medium', 'large') if any('/' + level + '/' in '/' + p for p in paths)}
            for d in cat.definitions:
                if d['error_code'] == 'UNCLASSIFIED':
                    continue
                meaning = cat.headers.get(d['error_code'], (None, d['error_code'], ''))[1] if version == 'original' else d['error_code']
                key = (version, d['error_code'], d['check_category'], d['check_subcategory'], meaning)
                g = groups.setdefault(key, dict(error_code=d['error_code'], check_category=d['check_category'],
                    check_subcategory=d['check_subcategory'], description=meaning, correction_version=version,
                    definitions=0, levels=set(), comments=set(), references=set()))
                g['definitions'] += 1
                g['levels'].update(levels)
                g['comments'].add(d['correction_comment'])
                # Reference each unique definition in a canonical file when available.
                source = next((p for p in sorted(paths) if p.startswith('scenarios/')), sorted(paths)[0])
                g['references'].add(f'{source}:{d["correction_line"]}')
        return [{**{k: v for k, v in g.items() if not isinstance(v, set)},
                 'lab_sizes': ', '.join(sorted(g['levels'])), 'original_comment': '\n'.join(sorted(g['comments'])),
                 'references': '\n'.join(sorted(g['references']))} for g in groups.values()]

    def grouped_errors(self):
        groups = collections.defaultdict(list)
        for r in self.epr:
            if r['analysis_included']:
                groups[tuple(r[k] for k in GROUP_KEYS)].append(r)
        output = []
        for key, rows in sorted(groups.items()):
            yes = sum(r['error_present'] == 1 for r in rows)
            no = sum(r['error_present'] == 0 for r in rows)
            executed = sum(r['executed_checks'] for r in rows)
            passed = sum(r['passed_checks'] for r in rows)
            failed = sum(r['failed_checks'] for r in rows)
            output.append(dict(zip(GROUP_KEYS, key)) | dict(runs=len(rows), evaluable_runs=yes + no,
                runs_with_error=yes, runs_without_error=no, unknown_runs=len(rows) - yes - no,
                error_frequency_percentage=percentage(yes, yes + no), executed_checks=executed,
                passed_checks=passed, failed_checks=failed, success_percentage=percentage(passed, executed),
                failure_percentage=percentage(failed, executed)))
        return output

    def summary(self):
        groups = collections.defaultdict(list)
        for e in self.evaluations:
            if e['analysis_included']:
                identity = self.base_identity(e)
                groups[tuple(identity[k] for k in SUMMARY_KEYS)].append(e)
        output = []
        for key, values in sorted(groups.items()):
            evaluated = [e for e in values if e['report_consistent']]
            passed = sum(e['csv_success'] is True for e in evaluated)
            runs = [self.run_rows[e['execution_id']] for e in values]
            ids = {e['evaluation_id'] for e in values}
            codes = {r['error_code'] for r in self.epr if r['evaluation_id'] in ids and r['failed_checks'] and r['error_code'] != 'UNCLASSIFIED'}
            output.append(dict(zip(SUMMARY_KEYS, key)) | dict(runs=len(values),
                completed_runs=sum(e['status'] == 'COMPLETED' for e in values), evaluated_runs=len(evaluated),
                fully_successful_runs=passed, run_success_percentage=percentage(passed, len(evaluated)),
                mean_check_success_percentage=mean([percentage(e['raw_totals']['PASS'], e['raw_totals']['PASS'] + e['raw_totals']['FAIL']) for e in evaluated]),
                mean_generation_seconds=mean([r.get('agent_seconds') for r in runs]),
                median_generation_seconds=median([r.get('agent_seconds') for r in runs]),
                mean_total_tokens=mean([r.get('total_tokens') for r in runs]), median_total_tokens=median([r.get('total_tokens') for r in runs]),
                failed_checks=sum(e['raw_totals']['FAIL'] for e in values), distinct_error_codes_observed=len(codes),
                checker_technical_errors=sum(e['status'] == 'CHECKER_FAILED' for e in values)))
        return output

    def validation(self):
        return dict(experiment=EXPERIMENT, statistics=dict(self.stats),
            classification_coverage_percentage=percentage(self.stats['classified_imported'], self.stats['imported_controls']),
            unique_error_codes=len({d['error_code'] for c in self.catalogs.values() for d in c.definitions if d['error_code'] != 'UNCLASSIFIED'}),
            corrections=len(self.catalogs), source_files=list(self.inventory.values()), issues=self.issues,
            policies=dict(original_history='preserved with separate correction_version; excluded from primary aggregates',
                v3_retry='latest completed report preferred, then completed evaluation; all additional attempts preserved',
                dns_record_success='no row-position mapping; missing identifiers are UNCLASSIFIED',
                no_code='implicit device/topology V3 checks have no invented CS code',
                expected_denominators='per-code expected counts come from correction. Ambiguous observed rows are UNCLASSIFIED; expected counts for named codes may overlap that unresolved pool and must not be summed across codes.',
                identifiability_bias='CS10/CS11 generic successful DNS rows lack identifiers. Code-specific run frequencies are conditional on identifiable outcomes and must not be interpreted as unbiased error prevalence.',
                native_variable_cardinality='route checks can emit several failures for one definition; every CSV row preserved',
                overlap_versions='definitions linked only by exact command+device+expected value or exact native definition; no equivalence inferred from similar names',
                snapshots='only the correction snapshot verified against its recorded hash classifies evaluation rows'))


class ExcelSink:
    def __init__(self, max_rows=1048576):
        from openpyxl import Workbook
        self.wb = Workbook(write_only=True)
        self.max_rows = max_rows
        self.counts = {}
        self.long_text = []

    def sheet(self, name, fields, rows, split=False):
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
        index, ws, count = 0, None, 0
        for row in rows:
            if ws is None or count >= self.max_rows:
                index += 1
                title = f'{name}_{index:02d}' if split else name if index == 1 else f'{name}_{index:02d}'
                ws = self.wb.create_sheet(title)
                ws.freeze_panes = 'A2'
                ws.sheet_view.showGridLines = False
                for i, field in enumerate(fields, 1):
                    width = 22
                    if any(s in field for s in ('description', 'comment', 'reason', 'path', 'source', 'command', 'detail')):
                        width = 48
                    if field.endswith('id') or field in ('execution_id', 'evaluation_id'):
                        width = 40
                    ws.column_dimensions[get_column_letter(i)].width = width
                header = []
                for field in fields:
                    cell = WriteOnlyCell(ws, field)
                    cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
                    cell.fill = PatternFill('solid', fgColor='17365D')
                    cell.alignment = Alignment(wrap_text=True, vertical='center')
                    header.append(cell)
                ws.append(header)
                ws.row_dimensions[1].height = 42
                count = 1
            values = []
            for field in fields:
                value = row.get(field)
                if isinstance(value, (dict, list, tuple, set)):
                    value = dumps(value)
                if isinstance(value, float) and not math.isfinite(value):
                    value = None
                if isinstance(value, str) and len(value) > 32767:
                    ident = digest(value)
                    self.long_text.append(dict(text_id=ident, source_sheet=ws.title, source_row=count + 1,
                                               source_column=field, full_text=value))
                    value = value[:30000] + f' [FULL TEXT: Long_Text/{ident}]'
                cell = WriteOnlyCell(ws, value)
                if isinstance(value, str):
                    cell.data_type = 's'  # Commands beginning with = remain literal data.
                if isinstance(value, float):
                    cell.number_format = '0.00'
                values.append(cell)
            ws.append(values)
            count += 1
            self.counts[ws.title] = count - 1
        if ws is None:
            ws = self.wb.create_sheet(name + '_01' if split else name)
            ws.append(fields)
            self.counts[ws.title] = 0
        # Filters are metadata only and don't materialize cells.
        for s in self.wb.worksheets:
            if s.title == name or s.title.startswith(name + '_'):
                s.auto_filter.ref = f'A1:{get_column_letter(len(fields))}{self.counts.get(s.title, 0) + 1}'

    def finish(self, path):
        if self.long_text:
            chunks = []
            for item in self.long_text:
                for n, start in enumerate(range(0, len(item['full_text']), 30000), 1):
                    chunks.append({k: v for k, v in item.items() if k != 'full_text'} | dict(part=n, text=item['full_text'][start:start + 30000]))
            self.sheet('Long_Text', ['text_id', 'source_sheet', 'source_row', 'source_column', 'part', 'text'], chunks)
        self.wb.save(path)


def export(builder, path, max_rows):
    sink = ExcelSink(max_rows)
    run_fields = list(dict.fromkeys([*IDENTITY, *(k for r in builder.run_rows.values() for k in r)]))
    sink.sheet('Runs', run_fields, builder.run_rows.values())
    def checks(where=''):
        for data, in builder.db.execute('SELECT data FROM checks ' + where + ' ORDER BY n'):
            yield json.loads(data)
    sink.sheet('Checks_All', CHECK_FIELDS, checks(), split=True)
    cat = builder.catalog_rows()
    sink.sheet('Error_Catalog', ['error_code', 'check_category', 'check_subcategory', 'description', 'original_comment',
                               'correction_version', 'lab_sizes', 'definitions', 'references'], cat)
    sink.sheet('Errors_Per_Run', EPR_FIELDS, builder.epr)
    sink.sheet('Errors_Per_Group', GROUP_FIELDS, builder.grouped_errors())
    codes = sorted({r['error_code'] for r in builder.epr})
    matrix = {}
    for row in builder.epr:
        matrix.setdefault(row['evaluation_id'], {k: row.get(k) for k in [*IDENTITY, 'correction_version', 'evaluation_id', 'analysis_included']})[row['error_code']] = row['error_present']
    sink.sheet('Error_Matrix', [*IDENTITY, 'correction_version', 'evaluation_id', 'analysis_included', *codes], matrix.values())
    sink.sheet('Summary', SUMMARY_FIELDS, builder.summary())
    validation_rows = [dict(kind='metric', source=k, detail=v, severity='info') for k, v in builder.stats.items()]
    validation_rows += [dict(kind='policy', source=k, detail=v, severity='info') for k, v in builder.validation()['policies'].items()]
    validation_rows += [dict(kind='source_file', source=v['path'], detail=dumps(v), severity='info') for v in builder.inventory.values()]
    validation_rows += [dict(kind=v['type'], source=v['source'], detail=v['detail'], severity=v['severity']) for v in builder.issues]
    sink.sheet('Validation', ['kind', 'source', 'detail', 'severity'], validation_rows)
    sink.sheet('Unclassified', CHECK_FIELDS, checks('WHERE classified=0'))
    eval_rows = []
    for e in builder.evaluations:
        row = builder.base_identity(e) | dict(status=e['status'], task_success=e['task_success'],
            correction_path=builder.rel(e['correction']), results_path=builder.rel(e['results']),
            source_metadata=builder.rel(e['source']), manifest_json=dumps(e['manifest']), metrics_json=dumps(e['metrics']))
        eval_rows.append(row)
    sink.sheet('Evaluation_Metadata', [*IDENTITY, 'correction_version', 'evaluation_id', 'analysis_included', 'status',
                                     'task_success', 'correction_path', 'results_path', 'source_metadata', 'manifest_json', 'metrics_json'], eval_rows)
    sink.finish(path)
    return sink.counts


def verify_xlsx(path, expected):
    # Stream XML directly: verifies every sheet and cell type without building a
    # second workbook in memory. No formulas or raw errors are executable cells.
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    counts = {}
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP corrotto: {bad}')
        names = [s.attrib['name'] for s in ET.fromstring(archive.read('xl/workbook.xml')).find(ns + 'sheets')]
        for index, name in enumerate(names, 1):
            rows, formula, errors = 0, 0, 0
            with archive.open(f'xl/worksheets/sheet{index}.xml') as stream:
                for _, element in ET.iterparse(stream, events=('end',)):
                    if element.tag == ns + 'row':
                        rows += 1
                        formula += sum(c.find(ns + 'f') is not None for c in element)
                        errors += sum(c.attrib.get('t') == 'e' for c in element)
                        element.clear()
            counts[name] = rows - 1
            if formula or errors or counts[name] != expected[name]:
                raise ValueError(f'Workbook non verificato: {name}, rows={counts[name]}, expected={expected[name]}, errors={errors}')
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/dns_skill_pilot_v2_classified')
    parser.add_argument('--max-sheet-rows', type=int, default=1048576)
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / 'outputs') or args.max_sheet_rows < 2 or args.max_sheet_rows > 1048576:
        parser.error('Output richiesto sotto outputs/ e limite righe tra 2 e 1048576')
    output.mkdir(parents=True, exist_ok=True)
    import fcntl
    with (output / '.build.lock').open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Un consolidamento è già attivo')
        with tempfile.TemporaryDirectory(prefix='dns-consolidation-') as tmp:
            db = sqlite3.connect(Path(tmp) / 'checks.sqlite')
            builder = Builder(root, db)
            print('Inventario originali, correction e rivalutazioni V3...', flush=True)
            builder.discover()
            if not builder.run_rows:
                raise SystemExit('Nessuna generazione originale individuata')
            print(f'{len(builder.run_rows)} generazioni, {len(builder.evaluations)} valutazioni incluse cronologie.', flush=True)
            for n, evaluation in enumerate(builder.evaluations, 1):
                builder.process_evaluation(evaluation)
                if n % 30 == 0:
                    print(f'Importate {n}/{len(builder.evaluations)} valutazioni; {builder.stats["checks_all_rows"]} righe', flush=True)
            builder.stats['error_catalog_codes'] = len({d['error_code'] for c in builder.catalogs.values() for d in c.definitions if d['error_code'] != 'UNCLASSIFIED'})
            builder.stats['original_history_evaluations'] = sum(e['correction_version'].startswith('original_history') for e in builder.evaluations)
            # Validate physical generations and all source inputs again before publishing.
            after = sorted((root / 'runs' / EXPERIMENT).glob('*/*/*/*/*/r*/manifest.json'))
            if after != builder.original_manifests:
                raise ValueError('Inventario originali cambiato durante il consolidamento')
            for source, recorded in builder.inventory.items():
                path = Path(source)
                if sha_file(path) != recorded['sha256']:
                    raise ValueError(f'File sorgente cambiato durante il consolidamento: {path}')
            print('Scrittura workbook in streaming...', flush=True)
            staging = output / 'dns_skill_pilot_v2_classified.build.xlsx'
            counts = export(builder, staging, args.max_sheet_rows)
            print('Verifica integrale dei fogli Excel...', flush=True)
            counts = verify_xlsx(staging, counts)
            for source, recorded in builder.inventory.items():
                if sha_file(Path(source)) != recorded['sha256']:
                    raise ValueError(f'File sorgente cambiato durante la scrittura Excel: {source}')
            validation = builder.validation()
            validation['workbook_sheets'] = counts
            validation['integrity'] = dict(original_inventory_unchanged=True, source_hashes_verified=True,
                run_count_matches_originals=len(builder.run_rows) == len(builder.original_manifests),
                workbook_all_sheet_counts_verified=True, raw_outcomes_preserved=True)
            final = output / 'dns_skill_pilot_v2_classified.xlsx'
            staging.replace(final)
            validation['workbook_sha256'] = sha_file(final)
            report = output / 'validation.json'
            report.write_text(dumps(validation) + '\n')
            db.close()
            print(dumps({'workbook': str(final), 'validation': str(report), 'statistics': validation['statistics'],
                         'coverage': validation['classification_coverage_percentage'], 'issues': len(builder.issues)}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
