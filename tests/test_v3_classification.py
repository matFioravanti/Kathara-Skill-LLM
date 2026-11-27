from pathlib import Path

import pytest
import yaml

from benchmark_core.v3_classification import correction_codes, classify_checks


@pytest.mark.parametrize('lab,level,count', [('lab_01', 'small', 73), ('lab_02', 'medium', 144), ('lab_03', 'large', 272)])
def test_all_v3_commands_have_exact_codes(lab, level, count):
    root = Path(__file__).resolve().parents[1]
    content = (root / 'scenarios' / lab / 'tasks/base' / level / f'correction_{level}_custom_v3.yaml').read_bytes()
    data = yaml.safe_load(content)
    index = correction_codes(content)
    assert len(index) == count
    checks = [{'test_description': f"Checking the exit code of the command '{c['command']}' on '{device}'",
               'passed': False, 'reason': 'failed'}
              for device, commands in data['test']['custom_commands'].items() for c in commands]
    rows = classify_checks(checks, content)
    assert all(r['test_code'] and r['classification_source'] == 'correction_comment_exact' for r in rows)
    assert all(r['primary_category'] == 'dns' for r in rows)
    assert all(r['passed'] is False and r['reason'] == 'failed' for r in rows)


def test_unknown_command_or_device_does_not_inherit_comment():
    content = b'''test:
  custom_commands:
    pc1:
      # DNS_AUTH_A_RECORD - test
      - command: 'dig @10.0.0.1 example.com A'
        exit_code: 0
      - command: 'echo unlabelled'
        exit_code: 0
'''
    checks = [{'test_description': f"Checking the exit code of the command '{cmd}' on '{device}'"}
              for cmd, device in [('dig @10.0.0.1 example.com A', 'pc1'),
                                   ('dig @10.0.0.1 example.com A', 'pc2'), ('echo unlabelled', 'pc1')]]
    rows = classify_checks(checks, content)
    assert [r['test_code'] for r in rows] == ['DNS_AUTH_A_RECORD', '', '']
    assert rows[0]['record_type'] == 'A'


def test_native_checks_retain_standard_classification():
    row = classify_checks([{'test_description': 'Verifying `10.0.0.1` reachable from device `pc1`'}], b'test: {}')[0]
    assert row['primary_category'] == 'network' and row['subcategory'] == 'reachability'
