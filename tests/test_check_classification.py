import collections
import json
from pathlib import Path

from benchmark_core.aggregation import _check_records, _run_record, _summary_records
from benchmark_core.check_classification import classify, classify_rows

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/thesis_final/lab_03/base/large/T1/dns_only/r001'


def test_historical_reference():
    manifest = json.loads((RUN / 'manifest.json').read_text())
    record = _run_record(json.loads((RUN / 'evaluation/metrics.json').read_text()), manifest)
    rows = _check_records(RUN, record)
    assert record['report_coverage'] == 'complete'
    assert len(rows) == 5562
    assert (record['network_total'], record['dns_total'], record['other_total']) == (4667, 895, 0)
    for group in ('network', 'dns', 'other'):
        assert record[f'{group}_passed'] + record[f'{group}_failed'] == record[f'{group}_total']
    counts = collections.Counter((r['subcategory'], r['record_type'], r['classification_source']) for r in rows)
    assert counts['dns_record', 'A', 'correction_order_0.1.14'] == 440
    assert counts['dns_record', 'MX', 'correction_order_0.1.14'] == 40
    assert counts['dns_record', 'MX', 'custom_command'] == 4
    assert sum(v for (sub, _, _), v in counts.items() if sub == 'dns_soa') == 49
    assert sum(v for (sub, _, _), v in counts.items() if sub == 'dns_delegation') == 48


def test_inconsistent_record_order_is_unknown(tmp_path):
    correction = tmp_path / 'correction.yaml'
    correction.write_text('test:\n  applications:\n    dns:\n      records:\n        A: {example.org: [1.2.3.4]}\n        MX: {example.org: [mail.example.org]}\n      local_ns: {"1.2.3.4": [pc1]}\n')
    rows = [dict(test_description='Checking correctness of DNS records', passed=True, reason='OK'),
            dict(test_description='Checking correctness of DNS records', passed=False, reason='pc1 resolve A example.org with IP x')]
    assert [x[2] for x in classify_rows(rows, correction, '0.1.14', True)] == ['unknown', 'unknown']
    rows[1]['reason'] = "pc1 resolve MX example.org with IP x instead of ['mail.example.org']"
    assert [x[2] for x in classify_rows(rows, correction, '0.1.14', True)] == ['A', 'MX']
    for version, complete in [('0.1.15', True), ('0.1.14', False)]:
        assert all(x[2] == 'unknown' for x in classify_rows(rows, correction, version, complete))


def test_custom_and_unknown():
    def custom(cmd):
        return classify(f"Checking the exit code of the command '{cmd}' on 'pc1'")
    assert custom('ip -4 route show default')[:2] == ('network', 'routing')
    assert custom('dig example.org SOA +norecurse')[:2] == ('dns', 'dns_soa')
    assert custom('dig @1.2.3.4 example.org NS +norecurse')[:2] == ('dns', 'dns_delegation')
    assert custom('dig example.org MX')[2] == 'MX'
    assert custom('dig x A # recursion-check')[:2] == ('dns', 'dns_recursion')
    assert classify('an unrelated MX routing dns sentence')[0] == 'unclassified'


def test_missing_report_is_not_zero(tmp_path):
    record = {'_evaluated': True, '_manifest': {}, 'checks_total': 2, 'checks_passed': 0}
    assert _check_records(tmp_path, record) == []
    assert record['report_coverage'] == 'missing'
    assert 'dns_total' not in record


def test_aggregate_repetitions_and_missing():
    common = {'_evaluated': True, 'report_coverage': 'complete', 'network_total': 2}
    rows = [{**common, 'network_pass_rate': value, 'pass_rate': value} for value in (1.0, 0.0, 0.5)]
    rows.append({**common, 'report_coverage': 'partial', 'network_pass_rate': 0.0})
    result = _summary_records(rows)[0]
    assert result['denominator_network_pass_rate'] == 3
    assert result['mean_network_pass_rate'] == .5
    assert result['stdev_network_pass_rate'] == .5
    assert result['partial_report_runs'] == 1


def test_partial_report_remains_inspectable(tmp_path):
    report = tmp_path / 'results/lab/lab_result_all.csv'
    report.parent.mkdir(parents=True)
    report.write_text('Test Description,Passed,Reason\nCheck existence of `r1`,False,missing\n')
    record = {'_evaluated': True, '_manifest': {}, 'checks_total': 2, 'checks_passed': 0}
    rows = _check_records(tmp_path, record)
    assert len(rows) == 1
    assert record['report_coverage'] == 'partial'
    assert 'network_total' not in record
