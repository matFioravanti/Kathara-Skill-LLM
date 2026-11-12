"""Standard benchmark supervision. Never imported by the COST266 runner."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
import signal
import subprocess
import tempfile
import time
import threading

from .workspace import utc_now, tree_hash


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
            out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


@dataclass(frozen=True)
class Policy:
    max_attempts: int = 3
    backoff_seconds: float = 5
    backoff_max_seconds: float = 60
    heartbeat_seconds: float = 10
    worker_timeout_seconds: float = 2400
    idle_timeout_seconds: float = 0
    memory_limit_mb: float = 4096
    cleanup_grace_seconds: float = 90
    auth_max_attempts: int = 3
    auth_wait_seconds: float = 300
    auth_poll_seconds: float = 15
    auto_resume: bool = True

    @classmethod
    def from_config(cls, config):
        raw = config.data.get('resilience', {})
        if not isinstance(raw, dict) or set(raw)-set(cls.__dataclass_fields__):
            raise ValueError('Configurazione resilience non valida')
        result = cls(**raw)
        for key, value in vars(result).items():
            if key == 'auto_resume':
                if type(value) is not bool: raise ValueError(key)
            elif (isinstance(value, bool) or not isinstance(value, (int,float)) or
                  not math.isfinite(value) or value < 0):
                raise ValueError(f'resilience.{key} non valido')
        for key in ('max_attempts', 'auth_max_attempts'):
            if type(getattr(result,key)) is not int or getattr(result,key)<1: raise ValueError(key)
        for key in ('heartbeat_seconds','worker_timeout_seconds','cleanup_grace_seconds','auth_poll_seconds'):
            if getattr(result,key)<=0: raise ValueError(key)
        return result


class RecoveryRequired(RuntimeError): pass


@contextmanager
def serial_lock():
    # All standard launchers of this user share the lock, including auth recovery.
    path = Path(tempfile.gettempdir()) / f'tesi-standard-{os.getuid()}.lock'
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryRequired('Un altro worker standard o recupero autenticazione è attivo') from None
        yield


def classify(message):
    text = message.lower()
    if any(s in text for s in ('auth_failed','unauthorized','401','token expired','expired token',
                              'refresh token','refresh_token','not authenticated','session expired','please sign in','login required')):
        return 'AUTH_FAILED'
    if any(s in text for s in ('integrity','alterato','hash','skill gate','skill_gate','violazione','cleanup','pulizia')):
        return 'INTEGRITY_FAILED'
    if any(s in text for s in ('timeout','timed out','timeouterror','watchdog')): return 'TIMEOUT'
    if any(s in text for s in ('429','rate limit','502','503','connection','temporar','network','overloaded')): return 'TRANSIENT'
    if 'memory' in text: return 'MEMORY_LIMIT'
    if 'crash' in text or 'keyboardinterrupt' in text: return 'CRASH'
    return 'PERMANENT'


def load(path):
    return json.loads(Path(path).read_text())


def error_kind(run):
    data = load(run/'manifest.json')
    text = data.get('pipeline_error','')
    # Read bounded tails; never copy exception text/credentials to supervisor logs.
    for name in ('logs/aut/stderr.log','logs/pipeline_error.log','logs/checker_stderr.log'):
        path = run/name
        if path.is_file():
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-65536))
                text += stream.read().decode('utf-8',errors='replace')
    if data.get('sandbox_cleanup_ok') is False: return 'INTEGRITY_FAILED'
    return classify(text)


def validate_artifacts(run, expected, completed=False):
    from .fingerprint import compare
    from .experiment import completed_artifact_error
    m = load(run/'manifest.json')
    if m.get('experimental_conditions'):
        status, reasons = compare(m, expected)
        if status != 'compatible': raise ValueError('Condizioni ripresa non valide: '+', '.join(reasons))
    else:
        for key in ('agent','model','reasoning_effort','skill_mode','source_lab_sha256','correction_sha256','prompt_sha256'):
            if m.get(key) != expected.get(key): raise ValueError('Condizione ripresa alterata: '+key)
    for relative, key in (('input/lab','input_lab_sha256'),('lab','final_lab_sha256')):
        if not m.get(key) or tree_hash(run/relative)!=m[key]: raise ValueError('Hash ripresa alterato: '+relative)
    for name,prefix in (('kathara-dns','dns_skill'),('kathara-creation','creation_skill')):
        if name in expected.get('skills',{}):
            if (m.get(prefix+'_sha256')!=expected['skills'][name]['sha256'] or
                m.get(prefix+'_bundle_sha256')!=expected['skills'][name]['bundle_sha256']):
                raise ValueError('Skill ripresa incoerente')
    if completed and m.get('experiment_id'):
        err = completed_artifact_error(SimpleNamespace(run=run,manifest=m,replicate=m['replicate']))
        if err: raise ValueError(err)
    elif completed:
        from .checker_runner import parse_reports
        metrics = load(run/'evaluation/metrics.json')
        parsed,_ = parse_reports(run/'results')
        if (metrics.get('status')!='COMPLETED' or m.get('checker_execution_success') is not True or
            parsed['task_success']!=m.get('task_success') or
            metrics['checker']['total']!=parsed['checks_total'] or metrics['checker']['passed']!=parsed['checks_passed']):
            raise ValueError('Report completato incoerente')
    snapshot=run/'evaluation/correction.yaml'
    if snapshot.exists() and hashlib.sha256(snapshot.read_bytes()).hexdigest()!=m['correction_sha256']:
        raise ValueError('Snapshot correction alterato')
    return m


def aut_receipt(run):
    native={'events.jsonl','result.json','prompt_sent.md','invocation.json'}
    paths=sorted(p for p in (run/'logs/aut').rglob('*') if p.is_file() and (p.name in native or p.suffix=='.eval'))
    return {str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def check_receipt(run, receipt):
    if aut_receipt(run)!=receipt: raise ValueError('Artefatti AUT/token alterati rispetto al checkpoint')


def _worker(config, scenario, agent, prompt_type, kwargs, resume_run, journal):
    os.setsid()
    parent=os.getppid()
    def parent_guard():
        while os.getppid()==parent: time.sleep(1)
        os.kill(os.getpid(),signal.SIGINT)
    threading.Thread(target=parent_guard,daemon=True).start()
    # Record only resource identities BEFORE creation; no command/stdin/token is stored.
    native = subprocess.Popen
    state = {'pid':os.getpid(), 'resources':[], 'run':str(resume_run) if resume_run else None}
    def save(): atomic_json(journal,state)
    class TrackedPopen(native):
        def __init__(self, args, *a, **kw):
            command = list(args) if isinstance(args,(list,tuple)) else []
            resource = None
            if command and Path(str(command[0])).name=='sbx' and 'create' in command and '--name' in command:
                resource={'kind':'sandbox','name':command[command.index('--name')+1]}
            elif 'kathara_lab_checker' in command and '--labs' in command:
                resource={'kind':'kathara','lab':str(Path(command[command.index('--labs')+1])/'lab')}
            if resource and resource not in state['resources']:
                state['resources'].append(resource); save()
            super().__init__(args,*a,**kw)
    subprocess.Popen=TrackedPopen
    original_callback=kwargs.pop('event_callback',None)
    def callback(event, **fields):
        if event=='run_started':
            state['run']=str(config.root/fields['run_path']); save()
        if event=='pipeline_state' and fields.get('state')=='AUT_COMPLETED' and state.get('run'):
            state['aut_receipt']=aut_receipt(Path(state['run'])); save()
        if original_callback: original_callback(event,**fields)
    save()
    try:
        from .pipeline import run_one, reevaluate_run
        if resume_run:
            result=reevaluate_run(config,resume_run)
        else:
            result=run_one(config,scenario,agent,prompt_type,event_callback=callback,**kwargs)
        state.update(run=str(result),finished=True); save()
    except BaseException as exc:
        state.update(finished=False,error_kind=classify(type(exc).__name__+': '+str(exc))); save()
        raise SystemExit(1) from None


def process_tree(pid):
    """Bounded ps snapshot: RSS in KiB; no command arguments or credentials."""
    result=subprocess.run(['ps','-axo','pid=,ppid=,rss='],capture_output=True,text=True,timeout=10)
    if result.returncode: raise RuntimeError('Impossibile monitorare i processi')
    rows=[tuple(map(int,line.split())) for line in result.stdout.splitlines() if len(line.split())==3]
    ids={pid}
    for _ in rows:
        more={p for p,parent,rss in rows if parent in ids}
        if more<=ids: break
        ids|=more
    return ids,sum(rss for p,parent,rss in rows if p in ids)/1024


def process_identity(pid):
    try:
        probe=subprocess.run(['ps','-p',str(pid),'-o','pid=,lstart='],capture_output=True,text=True,timeout=10)
        return probe.stdout.strip() if probe.returncode==0 else None
    except (OSError,subprocess.SubprocessError):
        return None


def stop_worker(worker, grace):
    try:
        ids,_=process_tree(worker.pid)
    except (OSError,RuntimeError,subprocess.SubprocessError):
        ids={worker.pid}
    identities={pid:process_identity(pid) for pid in ids if pid!=worker.pid}
    if worker.is_alive():
        try: os.kill(worker.pid,signal.SIGINT)
        except ProcessLookupError: pass
        worker.join(grace)
    for pid,identity in identities.items():
        if identity and process_identity(pid)==identity:
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
    if worker.is_alive(): worker.kill()
    worker.join()


def cleanup_resources(journal):
    """Retry cleanup only for exact resources registered by this worker."""
    if not Path(journal).exists(): return
    for item in load(journal).get('resources',[]):
        if item['kind']=='sandbox':
            from .docker_sandbox_runner import _sbx_rm, sbx_executable
            probe=subprocess.run([sbx_executable(),'ls','--json'],capture_output=True,text=True,timeout=30)
            if probe.returncode: raise RecoveryRequired('CLEANUP_FAILED: inventario sandbox non disponibile')
            inventory=json.loads(probe.stdout)
            if not isinstance(inventory,list): raise RecoveryRequired('CLEANUP_FAILED: inventario sandbox non valido')
            if not any(entry.get('name')==item['name'] for entry in inventory if isinstance(entry,dict)): continue
            ok,_=_sbx_rm(item['name'])
            if not ok: raise RecoveryRequired('CLEANUP_FAILED: sandbox da verificare')
        elif item['kind']=='kathara':
            lab=Path(item['lab'])
            if lab.is_dir():
                result=subprocess.run(['kathara','lclean'],cwd=lab,stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL,timeout=60)
                if result.returncode: raise RecoveryRequired('CLEANUP_FAILED: laboratorio da verificare')
            else:
                evidence=load(journal)
                cleanup=Path(evidence['run'])/'logs/kathara_cleanup.json' if evidence.get('run') else None
                if not cleanup or not cleanup.is_file() or load(cleanup).get('returncode')!=0:
                    raise RecoveryRequired('CLEANUP_FAILED: laboratorio temporaneo assente, verificare i residui Kathara')


def progress_signature(run):
    if not run: return ()
    entries=[]
    for path in list((run/'logs').rglob('*'))+[run/'manifest.json']:
        try:
            if path.is_file():
                info=path.stat(); entries.append((str(path),info.st_size,info.st_mtime_ns))
        except FileNotFoundError:
            continue  # reevaluation may atomically replace/remove an old log
    return tuple(entries)


def _attempt(config, scenario, agent, prompt_type, kwargs, resume_run, journal, policy, heartbeat):
    worker=multiprocessing.get_context('fork').Process(target=_worker,
        args=(config,scenario,agent,prompt_type,kwargs,resume_run,journal))
    worker.start(); started=last_change=time.monotonic(); previous=None; failure=None; ids={worker.pid}
    try:
        while worker.is_alive():
            ids,rss=process_tree(worker.pid)
            evidence=load(journal) if journal.exists() else {}
            run=Path(evidence['run']) if evidence.get('run') else None
            signature=progress_signature(run)
            if signature!=previous: last_change=time.monotonic(); previous=signature
            elapsed=time.monotonic()-started
            atomic_json(heartbeat,{'at':utc_now(),'pid':worker.pid,'elapsed_seconds':elapsed,'rss_mb':rss,'run':str(run) if run else None})
            print(f'[heartbeat] pid={worker.pid} elapsed={elapsed:.0f}s RAM={rss:.0f}MB',flush=True)
            if elapsed>policy.worker_timeout_seconds: failure='TIMEOUT'
            elif policy.idle_timeout_seconds and time.monotonic()-last_change>policy.idle_timeout_seconds: failure='TIMEOUT'
            elif policy.memory_limit_mb and rss>policy.memory_limit_mb: failure='MEMORY_LIMIT'
            if failure: break
            worker.join(policy.heartbeat_seconds)
    finally:
        if worker.is_alive(): stop_worker(worker,policy.cleanup_grace_seconds)
        else:
            worker.join()
            if worker.exitcode!=0:
                for pid in ids-{worker.pid}:
                    try: os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError: pass
        if failure or worker.exitcode!=0:
            cleanup_resources(journal)
    evidence=load(journal) if journal.exists() else {}
    if failure or worker.exitcode!=0:
        failure=failure or evidence.get('error_kind','CRASH')
    result=Path(evidence['run']) if evidence.get('run') else None
    worker.close()
    return result,failure


def recover_auth(policy, checkpoint, data):
    from .standard_auth import refresh_account
    for index in range(data.get('auth_attempts',0),policy.auth_max_attempts):
        data.update(status='RECOVERING_AUTH',auth_attempts=index+1); atomic_json(checkpoint,data)
        print(f'[AUTH_FAILED] ripristino {index+1}/{policy.auth_max_attempts}',flush=True)
        if refresh_account(): return True
        data['status']='WAITING_AUTH'; atomic_json(checkpoint,data)
        print('[WAITING_AUTH] eseguire codex login in un altro terminale; ripresa automatica entro la finestra configurata',flush=True)
        deadline=time.monotonic()+policy.auth_wait_seconds
        while time.monotonic()<deadline:
            time.sleep(min(policy.auth_poll_seconds,max(0,deadline-time.monotonic())))
            if refresh_account(): return True
        time.sleep(min(policy.backoff_max_seconds,policy.backoff_seconds*2**index))
    return False


def run_supervised(config, scenario, agent, prompt_type, *, resume_run=None, **kwargs):
    from .fingerprint import conditions, fingerprint
    policy=Policy.from_config(config)
    expected=conditions(config,scenario,prompt_type,kwargs.get('skill_mode') or ('dns_only' if agent=='codex' else 'no_skill'),kwargs.get('assignment'),agent=agent)
    identity=[kwargs.get('experiment_id'),scenario.scenario_id,str(kwargs.get('assignment')),prompt_type,kwargs.get('skill_mode'),kwargs.get('replicate',1)]
    directory=config.root/'runs/.supervision'/fingerprint(identity)
    directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/'checkpoint.json'
    with serial_lock():
        cleanup_blocked=config.root/'runs/.supervision/cleanup_blocked.json'
        if cleanup_blocked.exists():
            cleanup_resources(Path(load(cleanup_blocked)['journal']))
            cleanup_blocked.unlink()
        data=load(checkpoint) if checkpoint.exists() else {'schema':'standard_supervision_v1','conditions':expected,'attempts':[], 'auth_attempts':0}
        if data['conditions']!=expected: raise ValueError('Condizioni cambiate: checkpoint preservato')
        if not policy.auto_resume and data['attempts']: raise ValueError('Checkpoint già presente: scegliere una nuova ripetizione')
        # Adopt the last worker journal after a supervisor/host crash.
        if data['attempts'] and not data['attempts'][-1].get('finished_at'):
            journal=Path(data['attempts'][-1]['journal'])
            if journal.exists():
                evidence=load(journal)
                if evidence.get('run'): data['run']=evidence['run']
                if 'aut_receipt' in evidence: data['aut_receipt']=evidence['aut_receipt']
                if evidence.get('finished') is not True: cleanup_resources(journal)
        if not data.get('run') and not kwargs.get('experiment_id'):
            mode=expected['skill_mode']
            candidates=[]
            for path in (config.root/'runs'/scenario.scenario_id/prompt_type/mode).glob('r*/manifest.json'):
                m=load(path)
                if m.get('replicate',m.get('run_number'))==kwargs.get('replicate',1): candidates.append((path.parent,m))
            done=[(path,m) for path,m in candidates if m.get('pipeline_state')=='COMPLETED']
            if len(done)>1: raise ValueError('Run COMPLETED duplicate: selezione ambigua')
            if done: data['run']=str(done[0][0])
            else:
                recoverable=[(path,m) for path,m in candidates if m.get('aut_execution_success') is True]
                if len(recoverable)>1: raise ValueError('Run interrotte duplicate: selezione ambigua')
                if recoverable: data['run']=str(recoverable[0][0])
        if data.get('run'):
            run=Path(data['run'])
            # Reconcile crashes after a completed manifest, before supervisor checkpoint.
            if 'aut_receipt' in data: check_receipt(run,data['aut_receipt'])
            m=load(run/'manifest.json') if (run/'manifest.json').exists() else {}
            if m.get('pipeline_state')=='COMPLETED':
                validate_artifacts(run,expected,completed=True)
                data['status']='COMPLETED'; atomic_json(checkpoint,data); return run
            if m.get('aut_execution_success') is True:
                validate_artifacts(run,expected); resume_run=run
        if data.get('status')=='PERMANENT':
            if data.get('run'): return Path(data['run'])
            raise RecoveryRequired('PERMANENT: checkpoint preservato')
        if resume_run:
            validate_artifacts(resume_run,expected)
        if data.get('status') in ('AUTH_FAILED','WAITING_AUTH','RECOVERING_AUTH'):
            # A fresh invocation checks the restored session even if the old wait budget expired.
            from .standard_auth import refresh_account
            if not refresh_account(): raise RecoveryRequired('WAITING_AUTH: login interattivo ancora necessario')
        auth_blocked=config.root/'runs/.supervision/auth_blocked.json'
        if auth_blocked.exists():
            from .standard_auth import refresh_account
            if not refresh_account(): raise RecoveryRequired('WAITING_AUTH: nessuna nuova generazione avviata')
            auth_blocked.unlink()
        for number in range(len(data['attempts']),policy.max_attempts):
            journal=directory/f'worker_{number+1:03d}.json'
            data['attempts'].append({'number':number+1,'started_at':utc_now(),'journal':str(journal)})
            data['status']='RUNNING'; atomic_json(checkpoint,data)
            try:
                result,failure=_attempt(config,scenario,agent,prompt_type,dict(kwargs),resume_run,journal,policy,directory/'heartbeat.json')
            except RecoveryRequired:
                atomic_json(cleanup_blocked,{'journal':str(journal),'status':'CLEANUP_FAILED','at':utc_now()})
                raise
            if result:
                if journal.exists() and 'aut_receipt' in load(journal): data['aut_receipt']=load(journal)['aut_receipt']
                if 'aut_receipt' in data: check_receipt(result,data['aut_receipt'])
                data['run']=str(result)
                m=load(result/'manifest.json')
                if m.get('pipeline_state')=='COMPLETED':
                    validate_artifacts(result,expected,completed=True)
                    data['status']='COMPLETED'; data['attempts'][-1]['finished_at']=utc_now(); atomic_json(checkpoint,data); return result
                failure=failure or error_kind(result)
                if m.get('aut_execution_success') is True:
                    validate_artifacts(result,expected); resume_run=result
            failure=failure or 'CRASH'
            if failure=='INTEGRITY_FAILED':
                data['status']=failure; atomic_json(checkpoint,data)
                if result and load(result/'manifest.json').get('sandbox_cleanup_ok') is False:
                    atomic_json(cleanup_blocked,{'journal':str(journal),'status':'CLEANUP_FAILED','at':utc_now()})
                raise ValueError('Violazione integrità o cleanup: tentativo preservato')
            data.update(status=failure,last_error=failure)
            data['attempts'][-1].update(error=failure,run=str(result) if result else None,finished_at=utc_now())
            atomic_json(checkpoint,data)
            print(f'[recovery] attempt={number+1}/{policy.max_attempts} error={failure}',flush=True)
            if failure=='AUTH_FAILED':
                if not recover_auth(policy,checkpoint,data):
                    atomic_json(auth_blocked,{'at':utc_now(),'status':'WAITING_AUTH'})
                    data['status']='WAITING_AUTH'; atomic_json(checkpoint,data)
                    raise RecoveryRequired('WAITING_AUTH: stato salvato; riprendere dopo codex login')
            elif failure not in ('TRANSIENT','TIMEOUT','CRASH','MEMORY_LIMIT'):
                if result: return result
                raise RecoveryRequired(failure)
            if number+1<policy.max_attempts:
                time.sleep(min(policy.backoff_max_seconds,policy.backoff_seconds*2**number))
        data['status']='RETRY_EXHAUSTED'; atomic_json(checkpoint,data)
        if data.get('run'): return Path(data['run'])
        raise RecoveryRequired('RETRY_EXHAUSTED: tentativi conservati nel checkpoint')


def guarded_preflight(probe, config, agent, **kwargs):
    policy=Policy.from_config(config)
    with serial_lock():
        try:
            return probe(config,agent,**kwargs)
        except Exception as exc:
            if agent!='codex' or classify(str(exc))!='AUTH_FAILED': raise
            path=config.root/'runs/.supervision/preflight_auth.json'
            data={'status':'AUTH_FAILED','auth_attempts':0}
            if not recover_auth(policy,path,data):
                raise RecoveryRequired('WAITING_AUTH: preflight salvato, login necessario') from None
            return probe(config,agent,**kwargs)


def retry_reports(operation, config):
    policy=Policy.from_config(config)
    for number in range(policy.max_attempts):
        try:
            operation()
            (config.root/"runs/.supervision/report_failure.json").unlink(missing_ok=True)
            return True
        except (OSError,RuntimeError) as exc:
            print(f'[report] tentativo {number+1}: {type(exc).__name__}; run conservate',flush=True)
            if number+1<policy.max_attempts:
                time.sleep(min(policy.backoff_max_seconds,policy.backoff_seconds*2**number))
    atomic_json(config.root/'runs/.supervision/report_failure.json',{'at':utc_now(),'status':'REPORT_PENDING'})
    return False
