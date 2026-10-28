import json
from pathlib import Path

import openpyxl
import pytest

from benchmark_core.aut_observation import observe
from benchmark_core.aggregation import aggregate
from benchmark_core.skill_modes import SKILL_MODES, execution_prompt
from benchmark_core.run_metrics import make_metrics


def event(kind, ident, phase='completed', **kwargs):
    return {'type': 'item.' + phase, 'item': {'type': kind, 'id': ident, **kwargs}}


def observation(tmp_path, events, mode='both_forced', agent='codex', trace=True):
    path = tmp_path / 'logs/aut/events.jsonl'
    if trace:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(json.dumps(e) for e in events))
    return observe(tmp_path, {'agent': agent, 'skill_mode': mode}, events)


def test_web_lifecycle_and_shell_attempt(tmp_path):
    events = [event('web_search', 'a', 'started'), event('web_search', 'a', result={'url': 'https://kathara.org/docs'}),
              event('command_execution', 'b', command='curl https://example.com', exit_code=7, status='failed')]
    internet, _ = observation(tmp_path, events)
    assert (internet['web_search_calls'], internet['web_search_attempts'], internet['shell_network_candidates']) == (1, 1, 1)
    assert internet['internet_used'] is True
    assert internet['external_domains'] == ['kathara.org']
    internet, _ = observation(tmp_path, events[2:])
    assert internet['internet_used'] is None and internet['status'] == 'network_attempt_unconfirmed'


def test_missing_partial_logs(tmp_path):
    internet, skill = observation(tmp_path, [], trace=False)
    assert internet['internet_used'] is None and internet['web_search_calls'] is None
    assert skill['required_reads_observed'] is None
    internet, skill = observation(tmp_path, [event('web_search', 'a', 'started')])
    assert internet['web_search_attempts'] == 1 and internet['internet_used'] is None
    assert skill['status'] == 'unknown'


@pytest.mark.parametrize('skill,reader', [('kathara-dns', 'cat'), ('kathara-creation', "sed -n '1,240p'")])
def test_read_skill(tmp_path, skill, reader):
    e = event('command_execution', 'a', command=f'{reader} .codex/skills/{skill}/SKILL.md', exit_code=0, status='completed', aggregated_output=f'---\nname: {skill}\n---')
    _, compliance = observation(tmp_path, [e])
    assert compliance['skill_states'][skill] == 'observed'
    assert compliance['required_reads_observed'] is None


def test_both_modes_and_antigravity(tmp_path):
    es = [event('command_execution', s, command=f'cat .codex/skills/{s}/SKILL.md', exit_code=0, aggregated_output=f'name: {s}') for s in ('kathara-dns', 'kathara-creation')]
    _, skill = observation(tmp_path, es)
    assert skill['required_reads_observed'] is True and skill['status'] == 'verified'
    for mode in ('auto', 'no_skill'):
        _, skill = observation(tmp_path, [], mode=mode)
        assert skill['required_skills'] == [] and skill['status'] == 'not_required'
    _, skill = observation(tmp_path, [], mode='no_skill', agent='antigravity')
    assert skill['required_skills'] == ['kathara-dns'] and skill['status'] == 'unknown'
    for mode in ('creation_only', 'dns_only', 'both_forced'):
        for name in SKILL_MODES[mode].forced_skills:
            assert '$' + name in execution_prompt(mode, 'prompt') and name + '/SKILL.md' in execution_prompt(mode, 'prompt')
    assert execution_prompt('auto', 'prompt') == execution_prompt('no_skill', 'prompt') == 'prompt'


def test_results_and_legacy(tmp_path):
    run = tmp_path / 'runs/lab/T1/dns_only/r001'
    (run / 'evaluation').mkdir(parents=True)
    manifest = {'agent': 'codex', 'skill_mode': 'dns_only', 'scenario_id': 'lab', 'prompt_type': 'T1'}
    (run / 'manifest.json').write_text(json.dumps(manifest))
    metrics = make_metrics(run, manifest, total_seconds=None, checker_seconds=None, checker_outcome={'checks_passed': 1, 'checks_failed': 0, 'checks_total': 1, 'check_pass_rate': 1})
    assert metrics['checker']['passed'] == 1 and metrics['skill_compliance']['status'] == 'unknown'
    (run / 'evaluation/metrics.json').write_text(json.dumps(metrics))
    runs, checks, summary = aggregate(tmp_path / 'runs', tmp_path / 'results')
    assert runs.iloc[0]['internet_used'] is None
    assert summary.iloc[0]['internet_unknown_runs'] == 1
    assert summary.iloc[0]['skill_unobserved_or_unknown_runs'] == 1
    wb = openpyxl.load_workbook(tmp_path / 'results/benchmark.xlsx')
    assert 'internet_used' in [c.value for c in wb['Runs'][1]]
    assert 'skill_compliance_rate' in [c.value for c in wb['Summary'][1]]
    assert wb['Runs'].cell(2, list(runs.columns).index('internet_used') + 1).value is None
    metrics.pop('internet'); metrics.pop('skill_compliance')
    (run / 'evaluation/metrics.json').write_text(json.dumps(metrics))
    runs, _, _ = aggregate(tmp_path / 'runs', tmp_path / 'results')
    assert runs.iloc[0]['internet_used'] is None


def test_backfill_rolls_back_on_aggregation_error(tmp_path, monkeypatch):
    import sys
    from scripts import backfill_observations as backfill
    run = tmp_path / 'runs/lab/T1/no_skill/r001'
    (run / 'evaluation').mkdir(parents=True)
    (run / 'manifest.json').write_text(json.dumps({'agent': 'codex', 'skill_mode': 'no_skill'}))
    path = run / 'evaluation/metrics.json'
    path.write_text('{"checker": {"passed": 1}}')
    before = path.read_bytes()
    output = tmp_path / 'results'
    output.mkdir()
    report = output / 'runs.csv'
    report.write_text('original')
    def broken(runs, results):
        report.write_text('partial')
        raise RuntimeError('failure')
    monkeypatch.setattr(backfill, 'aggregate', broken)
    monkeypatch.setattr(sys, 'argv', ['backfill', '--runs', str(tmp_path / 'runs'), '--output', str(output)])
    with pytest.raises(RuntimeError):
        backfill.main()
    assert path.read_bytes() == before and report.read_text() == 'original'
