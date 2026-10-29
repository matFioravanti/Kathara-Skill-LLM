"""Bounded validation of the legacy pilot and ordinary recovery runner.

Run after deterministic tests. The default preserves the legacy two-case probe;
--recovery validates direct reading, recovery, fallback and the real checker.
Only isolated copies and existing sbx proxy authentication. No automatic reruns.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark_core.skill_gate import evaluate_read_evidence, certification_outcome
from benchmark_core.workspace import write_json, tree_hash
import yaml

OUT = Path(__file__).resolve().parents[1] / 'reports/skill_gate_pilot_v2'
AUT = yaml.safe_load((OUT.parents[1] / 'benchmark.yaml').read_text())['aut']


def call(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=kwargs.pop('timeout', 90), **kwargs)


def checked(args):
    r = call(args)
    if r.returncode:
        raise RuntimeError(f'{args[:3]}: {r.stderr}')
    return r.stdout


def run_case(root, positive):
    case = OUT / ('positive' if positive else 'negative')
    case.mkdir(parents=True, exist_ok=False)
    work, lab = root / ('work-' + case.name), root / ('lab-' + case.name)
    work.mkdir(mode=0o777); work.chmod(0o777)
    lab.mkdir(mode=0o777); lab.chmod(0o777)
    (lab / 'lab.conf').write_text('baseline\n'); (lab / 'lab.conf').chmod(0o666)
    skill = lab / '.codex/skills/kathara-dns/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('---\nname: kathara-dns\n---\nPilot only. Preserve the session secret in context.\n')
    metadata = {'agent': 'codex', 'skill_mode': 'dns_only', 'skill_protocol': 'enforced_read_v1', 'dns_skill_sha256': hashlib.sha256(skill.read_bytes()).hexdigest()}
    baseline = tree_hash(lab)
    secret = uuid.uuid4().hex
    record = {'checks': dict.fromkeys(('isolation', 'read', 'continuity', 'phase_b')), 'phase_b_started': False, 'model_attempts': 0, 'cleanup': []}
    active = None
    def create(readonly):
        nonlocal active
        active = 'tesi-pilot-' + uuid.uuid4().hex[:10]
        checked(['sbx', 'create', 'codex', str(work), str(lab) + (':ro' if readonly else ''), '--name', active, '--skills', 'off', '--pull', 'missing'])
        setup = "import pathlib,os; p=pathlib.Path('/tmp/gate-home'); p.mkdir(exist_ok=True); os.chown(p,65534,65534); c=pathlib.Path(" + repr(str(work / 'state')) + "); c.mkdir(exist_ok=True); os.chown(c,65534,65534); [(c/n).symlink_to('/home/agent/.codex/'+n) for n in ('config.toml','auth.json') if not (c/n).is_symlink()]"
        checked(['sbx','exec','-u','root',active,'python3','-c',setup])
    def prefix():
        return ['sbx','exec','-i','-w',str(lab),'-u','nobody','-e','HOME=/tmp/gate-home','-e','CODEX_HOME='+str(work/'state'), active,'setpriv','--no-new-privs']
    def remove():
        nonlocal active
        if active:
            r = call(['sbx','rm','--force',active]); record['cleanup'].append(r.returncode == 0)
            if r.returncode: raise RuntimeError('Sandbox cleanup failed: '+r.stderr)
            active = None
    def model(phase, prompt, session=None):
        logs = case / 'logs/aut' / phase; logs.mkdir(parents=True)
        args = ['codex','exec'] + (['resume',session] if session else []) + ['--json','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--disable','memories','-c','mcp_servers.mcp-gateway.enabled=false','-c','features.memories=false','--model',AUT['model'],'-c','model_reasoning_effort='+json.dumps(AUT['reasoning_effort']),'-']
        # The external mount, UID and no-new-privileges enforce confinement;
        # disabling Codex's inner policy makes write attempts observable.
        record['model_attempts'] += 1
        start = time.monotonic()
        try:
            r = call(prefix()+args, input=prompt, timeout=180)
        except subprocess.TimeoutExpired as e:
            def decoded(x): return x.decode() if isinstance(x, bytes) else (x or '')
            r = subprocess.CompletedProcess(args,124,decoded(e.stdout),decoded(e.stderr))
        (logs/'events.jsonl').write_text(r.stdout); (logs/'stderr.log').write_text(r.stderr)
        (logs/'prompt_sent.md').write_text(prompt)
        events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
        write_json(logs/'result.json',{'returncode':r.returncode,'timed_out':r.returncode==124,'seconds':time.monotonic()-start,'usage':[e.get('usage') for e in events if e.get('type')=='turn.completed']})
        return r, events
    try:
        create(True)
        servers = json.loads(checked(prefix()+['codex','-c','mcp_servers.mcp-gateway.enabled=false','mcp','list','--json']))
        if any(s.get('enabled') for s in servers): raise RuntimeError('Enabled MCP server')
        checked(prefix()+['codex','login','status'])
        # This audit runs AS A TOOL OF THE REAL CODEX PROCESS, reporting its
        # ancestry, privileges, mount table and actual blocked operations.
        audit = r'''
import os,pathlib,json,subprocess,socket
r={'uid':os.getuid(),'ancestry':[]}
p=os.getpid()
for _ in range(8):
 try:
  s=pathlib.Path('/proc/'+str(p)+'/status').read_text(); r['ancestry'].append(s); p=int(s.split('PPid:')[1].split()[0])
 except (OSError,ValueError): break
r['mountinfo']=pathlib.Path('/proc/self/mountinfo').read_text()
for name,path in [('lab_write','lab.conf'),('outside_write','/etc/gate-pilot-test'),('alternate_host','/Users/matthew/Desktop/Tesi-Skill/lab.conf')]:
 try: pathlib.Path(path).write_text('EARLY'); r[name]=True
 except OSError as e: r[name]=False; r[name+'_error']=str(e)
r['sudo']=subprocess.run(['sudo','-n','true'],capture_output=True).returncode==0
s=socket.socket(socket.AF_UNIX)
try: s.connect('/var/run/docker.sock'); r['docker_socket']=True
except OSError: r['docker_socket']=False
finally: s.close()
print(json.dumps(r))
'''
        prompt = 'Run this exact Python audit as a shell tool (python3 -c), and return its output. Do not substitute a claim for execution:\n'+audit
        prompt += '\nRemember this session secret, without writing it to any file: '+secret+'.\n'
        prompt += ('Then run a separate dedicated `cat .codex/skills/kathara-dns/SKILL.md` tool call. Stop afterward.' if positive else 'Do NOT read any SKILL.md. Stop after the audit. This is the negative control.')
        r, events = model('phase_a',prompt)
        verdict = evaluate_read_evidence(case,metadata,events,returncode=r.returncode,timed_out=r.returncode==124)
        record['gate'] = verdict
        record['checks']['read'] = not verdict['blocked'] if positive else None
        audits=[]
        for e in events:
            item=e.get('item',{})
            if e.get('type')=='item.completed' and item.get('type')=='command_execution':
                for line in item.get('aggregated_output','').splitlines():
                    try:
                        d=json.loads(line)
                        if isinstance(d,dict) and 'ancestry' in d: audits.append(d)
                    except ValueError: pass
        write_json(case/'security.json',{'audits':audits,'mcp_enabled':False,'baseline_unchanged':tree_hash(lab)==baseline})
        if audits:
            a=audits[-1]
            codex=[s for s in a['ancestry'] if s.startswith('Name:\tcodex\n')]
            record['checks']['isolation'] = bool(codex) and a['uid']!=0 and all('NoNewPrivs:\t1' in s and 'CapEff:\t0000000000000000' in s for s in codex) and not any(a[k] for k in ('lab_write','outside_write','alternate_host','sudo','docker_socket')) and tree_hash(lab)==baseline
        remove()
        if not positive:
            record['negative_control_passed'] = verdict['blocked'] and not record['phase_b_started'] and tree_hash(lab)==baseline
        elif not verdict['blocked'] and record['checks']['isolation'] is True:
            session=next((e.get('thread_id') for e in events if e.get('type')=='thread.started'),None)
            if not session: raise RuntimeError('No phase A thread ID')
            create(False)
            record['phase_b_started']=True
            r,b=model('phase_b','Continue this exact session. Write ONLY the session secret given in the previous turn to lab.conf using a tool. Do not read files to recover it.',session)
            b_id=next((e.get('thread_id') for e in b if e.get('type')=='thread.started'),None)
            record['checks']['continuity']=r.returncode==0 and b_id==session and (lab/'lab.conf').read_text().strip()==secret
            record['checks']['phase_b']=r.returncode==0 and (lab/'lab.conf').read_text().strip()==secret
            record['session_a']=session; record['session_b']=b_id
    except Exception as e:
        record['error']=str(e)
    finally:
        try: remove()
        except Exception as e: record['cleanup_error']=str(e)
        record['probe_outcome']=certification_outcome(record['checks'])
        # These probes do not exhaust alternate tool/service/socket paths in
        # the template. Do not promote an observed write denial to a complete
        # end-to-end security certification.
        record['certification_checks']={**record['checks'], 'isolation': None}
        record['certification']=certification_outcome(record['certification_checks'])
        record['security_scope']='Observed probes only; exhaustive alternate service/tool paths not verified'
        write_json(case/'validation.json',record)
    return record


def finalize_recovery_aut_artifacts(run, *, case, model, reasoning_effort, experiment_id='recovery_pilot'):
    """Derive telemetry from saved real turns, without another model call."""
    from benchmark_core.run_metrics import make_metrics
    from benchmark_core.skill_gate import read_gate_metrics
    gate=read_gate_metrics(run)
    metadata=json.loads((run/'manifest.json').read_text())
    metadata.update(agent='codex',model=model,reasoning_effort=reasoning_effort,
        scenario_id='pilot',prompt_type='T1',run_number=1,skill_mode='dns_only',
        skill_protocol='enforced_read_v1',experiment_id=experiment_id+'_'+case,
        run_id=experiment_id+'_'+case,execution_backend='docker_sandbox',
        available_skills=['kathara-dns'],forced_skills=['kathara-dns'],
        pipeline_state='AUT_COMPLETED',aut_execution_success=True,
        checker_execution_success=None,task_success=None,**gate)
    write_json(run/'manifest.json',metadata)
    # Namespace compatibility IDs even for the exploratory run preceding this
    # correction. Raw phase artifacts and model inputs remain unchanged.
    logs=run/'logs/aut'; events=[]
    phases=[logs/'phase_a']+sorted(p for p in (logs/'retries').glob('attempt_*') if p.is_dir())
    phases += [logs/p for p in ('fallback','phase_b') if (logs/p).is_dir()]
    for path in phases:
        for line in (path/'events.jsonl').read_text().splitlines():
            e=json.loads(line); name=str(path.relative_to(logs));e['_skill_gate_phase']=name
            if isinstance(e.get('item'),dict) and e['item'].get('id'):
                e['item']={**e['item'],'id':name+':'+e['item']['id']}
            events.append(e)
    (logs/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events))
    write_json(run/'evaluation/metrics.json',make_metrics(run,metadata,total_seconds=None,
        checker_seconds=None,checker_outcome=None))


def export_recovery_pilot(outputs, results):
    """Adapt retained case artifacts to the existing four-level run layout."""
    import shutil
    from benchmark_core.aggregation import aggregate
    sources=[p for output in outputs for p in output.glob('*/run') if (p/'evaluation/metrics.json').is_file()]
    if not sources: raise ValueError('No completed pilot metrics available for export')
    with tempfile.TemporaryDirectory(prefix='tesi-recovery-export-',dir='/private/tmp') as temporary:
        root=Path(temporary)
        for index,source in enumerate(sources):
            target=root/f'case_{index:02d}'/'T1/dns_only/r001';target.mkdir(parents=True)
            for relative in ('manifest.json','evaluation/metrics.json'):
                (target/relative).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source/relative,target/relative)
            if (source/'results').is_dir(): shutil.copytree(source/'results',target/'results')
        rows,checks,summary=aggregate(root,results)
        if len(rows)!=len(sources): raise RuntimeError('Pilot export silently omitted runs')
        print(json.dumps({'exported_runs':len(rows),'checks':len(checks),'summary_groups':len(summary),'output':str(results)}),flush=True)


def run_recovery_pilot():
    """Four bounded real-model cases through the ordinary runner.

    Only omitted read prompts are controlled interventions. No model output,
    gate decision, fallback delivery, continuity or checker result is mocked.
    """
    import copy
    import shutil
    from unittest.mock import patch
    from benchmark_core.config import Config
    from benchmark_core.docker_sandbox_runner import ProtectedCodexSession
    from benchmark_core.inspect_runner import run_aut
    from benchmark_core.pipeline import run_one
    from benchmark_core.scenario_loader import Scenario
    from benchmark_core.skill_modes import SKILL_CONFIG_KEYS
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--recovery',action='store_true')
    parser.add_argument('--case',choices=['immediate','retry','fallback','dns_real','all'],default='all')
    parser.add_argument('--output',type=Path,default=OUT.parent/'skill_gate_recovery_pilot')
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('--include',action='append',type=Path,default=[])
    parser.add_argument('--results',type=Path,default=OUT.parent/'skill_gate_recovery_results')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    if args.export_only:
        export_recovery_pilot([output]+args.include,args.results)
        return
    calls=0
    class PilotSession(ProtectedCodexSession):
        def turn(self,*,prompt,directory,timeout):
            nonlocal calls
            calls+=1
            if calls>16: raise RuntimeError('Pilot model-call budget exhausted')
            omit=(case=='retry' and directory.name=='phase_a') or (case=='fallback' and (directory.name=='phase_a' or directory.parent.name=='retries'))
            if omit:
                # Explicit experimental intervention; preserve requested input.
                directory.parent.mkdir(parents=True,exist_ok=True)
                (directory.parent/(directory.name+'_requested_prompt.md')).write_bytes(prompt)
                prompt=b'CONTROLLED READING OMISSION: Do not open files or call any tools in this turn. Reply READY and stop. The next turn will supply further instructions.'
            print(json.dumps({'case':case,'turn':str(directory.name),'controlled_omission':omit,'model_call':calls}),flush=True)
            return super().turn(prompt=prompt,directory=directory,timeout=timeout)
    cases=['immediate','retry','fallback','dns_real'] if args.case=='all' else [args.case]
    for case in cases:
        target=output/case
        if target.exists(): raise RuntimeError('Refusing automatic rerun of existing case: '+str(target))
        target.mkdir()
        summary={'case':case,'controlled_omission':case in ('retry','fallback'),'status':'NOT_RUN'}
        calls_before=calls
        with tempfile.TemporaryDirectory(prefix='tesi-recovery-pilot-',dir='/private/tmp') as temporary:
            root=Path(temporary); root.chmod(0o755)
            data=copy.deepcopy(yaml.safe_load((repo/'benchmark.yaml').read_text()))
            data['aut'].update(skill_protocol='enforced_read_v1',skill_gate_recovery_policy='recovery_v1',skill_gate_max_retries=2)
            scenario_id='lab00_five_router' if case=='dns_real' else 'pilot'
            scenario_root=root/'scenarios'/scenario_id
            try:
                if case=='dns_real':
                    shutil.copytree(repo/'scenarios'/scenario_id,scenario_root)
                    shutil.copytree(repo/'prompt'/scenario_id,root/'prompt'/scenario_id)
                    shutil.copytree(repo/'skills',root/'skills')
                    # Keep every source/expected instruction byte unchanged.
                    cfg=Config(root,data)
                    with patch('benchmark_core.docker_sandbox_runner.ProtectedCodexSession',PilotSession):
                        run=run_one(cfg,Scenario(scenario_id,scenario_root),'codex','T1','dns_only',experiment_id='recovery_v1_pilot')
                    manifest=json.loads((run/'manifest.json').read_text())
                    summary.update(status=manifest['pipeline_state'],checker_executed=manifest['checker_execution_success'],task_success=manifest['task_success'],error=manifest.get('pipeline_error'))
                else:
                    lab=scenario_root/'lab'; lab.mkdir(parents=True)
                    (lab/'lab.conf').write_text('r1[0]="A"\n')
                    skill=root/'skills/dns/SKILL.md'; skill.parent.mkdir(parents=True)
                    skill.write_text('---\nname: kathara-dns\ndescription: Tiny isolated recovery pilot instructions.\n---\nAfter the gate opens, write the literal text PILOT_READY to pilot.result if requested.\n')
                    data['aut']['dns_skill']='skills/dns/SKILL.md'
                    cfg=Config(root,data)
                    from benchmark_core.workspace import create_workspace
                    prompt='Write PILOT_READY to pilot.result in the current lab directory using a tool. Leave lab.conf unchanged.'
                    run=create_workspace(root/'runs',Scenario(scenario_id,scenario_root),'T1','dns_only',prompt)
                    write_json(run/'manifest.json',{'agent':'codex','skill_mode':'dns_only','skill_protocol':'enforced_read_v1','dns_skill_sha256':hashlib.sha256(skill.read_bytes()).hexdigest()})
                    with patch('benchmark_core.docker_sandbox_runner.ProtectedCodexSession',PilotSession):
                        run_aut(cfg,Scenario(scenario_id,scenario_root),run,'codex',prompt,skill_mode='dns_only')
                    summary.update(status='COMPLETED',configured=(run/'lab/pilot.result').read_text().strip()=='PILOT_READY')
                    finalize_recovery_aut_artifacts(run,case=case,model=cfg.model(),reasoning_effort=cfg.reasoning_effort(),experiment_id=output.name)
                shutil.copytree(run,target/'run')
                summary['gate']=json.loads((run/'logs/aut/skill_gate.json').read_text())
                if case=='dns_real': summary['metrics']=json.loads((run/'evaluation/metrics.json').read_text())
            except Exception as error:
                summary.update(status='FAILED',error=f'{type(error).__name__}: {error}')
                found=list((root/'runs').glob('*/*/*/r*'))
                if found and not (target/'run').exists(): shutil.copytree(found[0],target/'run')
            summary['model_calls']=calls-calls_before
            write_json(target/'validation.json',summary)
            print(json.dumps({k:v for k,v in summary.items() if k not in ('gate','metrics')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    if '--recovery' in sys.argv:
        run_recovery_pilot()
    else:
        OUT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='tesi-gate-pilot-',dir='/private/tmp') as d:
            root=Path(d); root.chmod(0o755)
            for positive in (True,False):
                print(json.dumps(run_case(root,positive)),flush=True)
