"""Orchestrazione incrementale: solo i file del lab attraversano le fasi."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import fcntl
import json
import math
import shutil
import subprocess
import tempfile
import time

from ..config import Config, skill_paths
from ..checker_runner import run_checker, checker_test_rows
from ..correction_input import read_correction
from ..inspect_runner import run_aut
from ..run_metrics import make_metrics
from ..skill_modes import mode_details
from ..workspace import (component_versions, copy_lab, manifest, manifest_changes, manifest_hash,
                         tree_hash, utc_now, write_json)
from .protocol import (Cell, Spec, STAGES, VERSION, clean_lab, digest, fingerprint,
                       prompts, safe_path, validate_backend, CONTINUOUS_VERSION, execution_mode, stage_requirements)


def read_json(path: Path) -> dict:
    safe_path(path)
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f'Oggetto JSON atteso: {path}')
    return data


@contextmanager
def experiment_lock(root: Path, experiment_id: str):
    # Lock esterno anche per una repository ancora senza runs/.
    path = Path(tempfile.gettempdir()) / ('cost266-' + fingerprint([str(root.resolve()), experiment_id]) + '.lock')
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Esperimento COST266 già in esecuzione') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def timed_config(config, timeout: int):
    data = deepcopy(config.data)
    data['benchmark']['timeout_seconds'] = timeout
    return Config(config.root, data)


def conditions(config, spec: Spec, cell: Cell, inventory: dict, preparation: dict) -> dict:
    validate_backend(config, cell.skill_mode, strategy=cell.strategy, protocol=spec.protocol)
    details = mode_details(cell.skill_mode)
    paths = skill_paths(config, details.available_skills)
    # Antigravity usa la Skill DNS anche in no_skill: mantiene la semantica standard.
    if config.data['aut']['agent'] == 'antigravity':
        paths = skill_paths(config, ('kathara-dns',))
    return {'protocol': spec.protocol, 'identity': cell.relative.as_posix(),
            'component_versions': component_versions(), 'repository_revision': _revision(config.root),
            'implementation_sha256': fingerprint({p.name:digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}),
            'baseline_sha256': preparation['baseline_sha256'], 'correction_sha256': preparation['correction_sha256'],
            'inventory_sha256': fingerprint(inventory), 'config_sha256': fingerprint(config.data),
            'oracle_coverage_sha256': digest((spec.dataset/'oracle_coverage.json').read_bytes()) if (spec.dataset/'oracle_coverage.json').exists() else None,
            'agent': config.data['aut']['agent'], 'model': config.model(), 'reasoning_effort': config.reasoning_effort(),
            'skill_mode': cell.skill_mode, 'skill_protocol': config.data['aut'].get('skill_protocol', 'explicit_read_v2'),
            'skill_bundles': {name: tree_hash(path.parent) for name, path in paths.items()},
            'budgets': [spec.stage_timeout, spec.total_timeout, spec.checker_timeout],
            'prompts': [digest(p.encode()) for p in prompts(inventory, cell)]}


def invariant_checks(baseline: Path, current: Path, inventory: dict):
    clean_lab(current)
    from .assets import interfaces
    base_interfaces, current_interfaces = interfaces(baseline), interfaces(current)
    if base_interfaces != current_interfaces:
        raise RuntimeError('Violazione protocollo: dispositivi/interfacce/link modificati')
    devices = set(base_interfaces)
    allowed = {'lab.conf', *devices, *(d+'.startup' for d in devices)}
    if any(p.name not in allowed for p in current.iterdir()):
        raise RuntimeError('Violazione protocollo: file non appartenenti al laboratorio')
    dns = {z['device'] for z in inventory['zones']} | {r['device'] for r in inventory['resolvers']}
    def fixed_conf(path):
        return [line for line in (path/'lab.conf').read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#') and not
                any(line.lstrip().startswith(device+'[image]') for device in dns)]
    if fixed_conf(baseline) != fixed_conf(current):
        raise RuntimeError('Violazione protocollo: lab.conf alterato oltre le immagini DNS')
    for device in devices:
        before = (baseline/f'{device}.startup').read_text()
        after = (current/f'{device}.startup').read_text()
        if not after.startswith(before):
            raise RuntimeError(f'Violazione protocollo: startup di rete modificato: {device}')
        appended = after[len(before):]
        import re
        if re.search(r'\b(?:ip|ifconfig|route|sysctl|iptables|nft)\b', appended):
            raise RuntimeError(f'Violazione protocollo: comandi di rete aggiunti: {device}')


def static_validation(lab: Path, inventory: dict, stage: int) -> dict:
    """Controllo intermedio limitato: presenza dichiarazioni, NON correttezza DNS."""
    import re
    checks = {}
    for zone in inventory['zones']:
        if zone['stage'] > stage:
            continue
        files = list((lab/zone['device']/'etc/bind').glob('*'))
        text = '\n'.join(p.read_text(errors='replace') for p in files if p.is_file())
        checks[zone['name']] = bool(re.search(r'\bzone\s+"'+re.escape(zone['name'].rstrip('.') or '.')+r'\.?"\s*\{', text))
    return {'kind': 'static_zone_declaration_presence', 'semantic_dns_validation': False,
            'checks': checks, 'passed': sum(checks.values()), 'total': len(checks),
            'pass_rate': sum(checks.values())/len(checks) if checks else None}


def _revision(root: Path):
    result = subprocess.run(['git','rev-parse','HEAD'], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _step_dirs(run: Path, count: int):
    for index in range(1, count+1):
        yield run/'steps'/f'{index:02d}'


def verify_run(run: Path, expected: dict) -> tuple[dict, list[dict]]:
    """Fail closed: ripresa solo da prefisso contiguo di checkpoint verificati."""
    metadata = read_json(run/'manifest.json')
    if metadata.get('conditions') != expected or metadata.get('conditions_sha256') != fingerprint(expected):
        raise ValueError('Condizioni/hash cambiati: resume rifiutato; usare un nuovo experiment_id')
    mode = execution_mode(expected['protocol'],metadata['strategy'])
    if metadata.get('execution_mode',mode) != mode:
        raise ValueError('Execution mode incoerente con protocollo/strategia della run')
    if tree_hash(run/'input/lab') != expected['baseline_sha256']:
        raise ValueError('Baseline input alterata')
    if digest((run/'evaluation/correction.yaml').read_bytes()) != expected['correction_sha256']:
        raise ValueError('Snapshot correction alterato')
    if expected.get('oracle_coverage_sha256') and digest((run/'evaluation/oracle_coverage.json').read_bytes()) != expected['oracle_coverage_sha256']:
        raise ValueError('Snapshot copertura oracle alterato')
    for entry in metadata.get('attempt_history', []):
        receipt_path = safe_path(run/entry['receipt'])
        if not receipt_path.is_relative_to(run) or digest(receipt_path.read_bytes()) != entry['sha256']:
            raise ValueError('Receipt tentativo alterato')
        receipt = read_json(receipt_path)
        attempt = receipt_path.parent
        for relative, sha in receipt['artifacts'].items():
            artifact = safe_path(attempt/relative)
            if not artifact.is_relative_to(attempt) or digest(artifact.read_bytes()) != sha:
                raise ValueError('Artefatti tentativo alterati')
        if tree_hash(attempt/'input/lab') != receipt['input_sha256']:
            raise ValueError('Input tentativo alterato')
    completed, gap = [], False
    previous = expected['baseline_sha256']
    for index, step in enumerate(_step_dirs(run, len(expected['prompts']))):
        marker = step/'completed.json'
        if not marker.exists():
            gap = True
            if (step/'checkpoint').exists():
                raise ValueError('Checkpoint senza marker di completamento')
            continue
        if gap:
            raise ValueError('Checkpoint non contigui')
        record = read_json(marker)
        if (record.get('input_sha256') != previous or record.get('prompt_sha256') != expected['prompts'][index]
                or tree_hash(step/'checkpoint') != record.get('checkpoint_sha256')):
            raise ValueError('Checkpoint/hash non valido')
        attempt = safe_path(step/record['attempt'])
        if not attempt.is_relative_to(step) or read_json(attempt/'manifest.json').get('pipeline_state') != 'COMPLETED':
            raise ValueError('Tentativo checkpoint non valido')
        for relative, sha in record['artifacts'].items():
            artifact = safe_path(attempt/relative)
            if not artifact.is_relative_to(attempt) or digest(artifact.read_bytes()) != sha:
                raise ValueError('Artefatti fase modificati')
        completed.append(record)
        previous = record['checkpoint_sha256']
    if expected.get('protocol') == CONTINUOUS_VERSION and metadata.get('strategy')=='incremental':
        identities = set()
        for step in list(_step_dirs(run,len(expected['prompts'])))[:len(completed)]:
            record = read_json(step/'completed.json')
            stage = read_json(step/record['attempt']/'manifest.json')
            identity = (stage.get('thread_id'),stage.get('sandbox_id'),stage.get('sandbox_name'))
            if (not all(isinstance(v,str) and v for v in identity) or stage.get('stage_completed') is not True
                    or stage.get('context_continuity_verified') is not True or stage.get('session_count')!=1):
                raise ValueError('Evidenza di continuità fase non valida')
            identities.add(identity)
        if len(identities)>1:
            raise ValueError('Thread o sandbox differenti tra checkpoint v2')
        if metadata.get('pipeline_state')=='COMPLETED' and (
                metadata.get('session_cleanup_ok') is not True or metadata.get('context_continuity_verified') is not True
                or metadata.get('session_count')!=1 or metadata.get('writable_sandbox_count')!=1
                or (metadata.get('thread_id'),metadata.get('sandbox_id'),metadata.get('sandbox_name')) not in identities):
            raise ValueError('Sessione continua COMPLETED priva di continuità/cleanup verificati')
    if metadata.get('pipeline_state') == 'COMPLETED':
        if len(completed) != len(expected['prompts']) or tree_hash(run/'lab') != previous:
            raise ValueError('Run COMPLETED priva del laboratorio finale valido')
        metrics = read_json(run/'evaluation/metrics.json')
        if metrics.get('status') != 'COMPLETED' or metadata.get('checker_execution_success') is not True:
            raise ValueError('Metriche finali mancanti o incoerenti')
        from ..checker_runner import parse_reports
        parsed, _ = parse_reports(run/'results')
        if metrics['checker']['passed'] != parsed['checks_passed'] or metrics['checker']['total'] != parsed['checks_total'] or metadata['task_success'] != parsed['task_success']:
            raise ValueError('Report checker e metriche incoerenti')
    return metadata, completed


def plan(config, spec, cell, inventory, preparation, *, resume=False, rerun=False):
    expected = conditions(config, spec, cell, inventory, preparation)
    run = safe_path(config.root/'runs'/cell.relative)
    if run.exists():
        metadata, completed = verify_run(run, expected)
        if rerun:
            if len(completed) != len(expected['prompts']):
                raise ValueError('AUT incompleto: impossibile rivalutare')
            if spec.protocol==CONTINUOUS_VERSION and cell.strategy=='incremental' and metadata.get('session_cleanup_ok') is not True:
                raise ValueError('Cleanup sessione non verificato: rivalutazione non consentita')
            return 'RECHECK', run
        if not resume:
            raise ValueError(f'Run già presente: {run}; usare --resume o un nuovo experiment_id')
        if metadata['pipeline_state'] == 'COMPLETED':
            return 'SKIP', run
        if spec.protocol == CONTINUOUS_VERSION and cell.strategy == 'incremental':
            if len(completed) < len(expected['prompts']):
                raise ValueError('Sessione continua terminata: --resume AUT richiede la stessa sandbox/thread; usare un nuovo experiment_id')
            if metadata.get('session_cleanup_ok') is not True:
                raise ValueError('Cleanup sessione non verificato: rivalutazione non consentita')
        # Nessun replay di un tentativo AUT che potrebbe essere stato interrotto:
        # si crea un nuovo tentativo preservando quello precedente.
        return 'RESUME', run
    if rerun:
        return 'MISSING', run
    return 'RUN', run


def _sum_known(values):
    return sum(values) if values and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in values) else None


def collect_metrics(run: Path, metadata: dict, *, checker_outcome=None) -> dict:
    # Unico parser dei token/tempi: make_metrics. Mai sommare events e result due volte.
    attempts = sorted((run/'steps').glob('*/attempts/*/evaluation/metrics.json'))
    stage_metrics = [read_json(path) for path in attempts]
    metrics = make_metrics(run, metadata, total_seconds=metadata.get('active_seconds',0),
                           checker_seconds=metadata.get('checker_seconds'), checker_outcome=checker_outcome)
    from ..token_usage import load_accounting, aggregate_accounting
    from ..run_metrics import accounting_fields
    if load_accounting(run/'logs/aut') is None:
        accounting = [load_accounting(p.parents[1]/'logs/aut') for p in attempts]
        if accounting and all(item is not None for item in accounting):
            metrics.update(accounting_fields(aggregate_accounting(accounting)))
    tokens = {key: _sum_known([m['tokens'].get(key) for m in stage_metrics])
              for key in ('input','output','reasoning','cached_input','cache_write_input','total','total_reported','total_calculated')}
    metrics['tokens'] = tokens
    metrics['timing']['agent_seconds'] = _sum_known([m['timing']['agent_seconds'] for m in stage_metrics])
    metrics['timing']['sandbox_overhead_seconds'] = _sum_known([m['timing'].get('sandbox_overhead_seconds') for m in stage_metrics])
    metrics['strategy'] = metadata['strategy']
    metrics['execution_mode'] = execution_mode(metadata['conditions']['protocol'],metadata['strategy'])
    metrics['stage_count'] = metadata['stage_count']
    metrics['completed_stages'] = sum(p.exists() for p in (run/'steps').glob('*/completed.json'))
    metrics['aut_calls'] = sum(m.get('aut_call_observed',False) for m in stage_metrics)
    metrics['sandbox_count'] = sum(1 for path in attempts if (path.parents[1]/'logs/aut/sandbox_metadata.json').exists())
    metrics['protocol_version'] = metadata.get('protocol_version') or metadata['conditions']['protocol']
    if metrics['protocol_version'] == CONTINUOUS_VERSION:
        metrics['functional_turns'] = metrics['aut_calls']
        session_file = run/'logs/aut/continuous_session.json'
        gate_turns = []
        if session_file.exists():
            session = read_json(session_file)
            gate_turns = read_json(run/'logs/aut/gate_turn_metrics.json')['turns']
            metrics.update({key:session.get(key) for key in (
                'sandbox_name','sandbox_id','thread_id','session_count','sandbox_count',
                'writable_sandbox_count','protected_sandbox_count','context_continuity_verified','session_wall_seconds')})
            metrics['session_cleanup_ok'] = session['cleanup_ok']
            metrics['timing']['sandbox_overhead_seconds'] = session['overhead_seconds']
            for key in tokens:
                tokens[key] = _sum_known([m['tokens'].get(key) for m in stage_metrics]+[t['tokens'].get(key) for t in gate_turns])
            metrics['timing']['agent_seconds'] = _sum_known(
                [m['timing']['agent_seconds'] for m in stage_metrics]+[t['agent_seconds'] for t in gate_turns])
        else:
            # One-shot v2 conserva run_aut e il gate ordinari. La metrica della
            # singola fase include già i turni protetti: qui si separano, non si risommano.
            from ..run_metrics import load_jsonl, accounted_codex_tokens
            from ..skill_gate import read_gate_metrics
            threads = set()
            environments = []
            for path in attempts:
                attempt = path.parents[1]
                logs = attempt/'logs/aut'
                for event in load_jsonl(logs/'events.jsonl'):
                    if event.get('type')=='thread.started' and event.get('thread_id'):
                        threads.add(event['thread_id'])
                sandbox = read_json(logs/'sandbox_metadata.json') if (logs/'sandbox_metadata.json').exists() else {}
                environments.extend(sandbox.get('environments') or ([sandbox] if sandbox else []))
                gate = read_gate_metrics(attempt)
                for part in [logs/'phase_a', *sorted((logs/'retries').glob('attempt_*')), logs/'fallback']:
                    if (part/'result.json').exists():
                        result = read_json(part/'result.json')
                        gate_turns.append({'tokens':accounted_codex_tokens(part,result),
                                           'agent_seconds':result.get('duration_seconds')})
            metrics.update(session_count=len(threads),thread_id=next(iter(threads)) if len(threads)==1 else None,
                sandbox_count=len(environments),writable_sandbox_count=metrics['functional_turns'],
                protected_sandbox_count=len(environments)-metrics['functional_turns'],
                context_continuity_verified=len(threads)==1)
        metrics['gate_turns'] = len(gate_turns)
        metrics['aut_calls'] += len(gate_turns)
        metrics['gate_agent_seconds'] = _sum_known([t['agent_seconds'] for t in gate_turns]) if gate_turns else 0
        metrics['gate_input_tokens'] = _sum_known([t['tokens']['input'] for t in gate_turns]) if gate_turns else 0
        metrics['gate_output_tokens'] = _sum_known([t['tokens']['output'] for t in gate_turns]) if gate_turns else 0
        if session_file.exists():
            metrics['functional_input_tokens'] = _sum_known([m['tokens']['input'] for m in stage_metrics])
            metrics['functional_output_tokens'] = _sum_known([m['tokens']['output'] for m in stage_metrics])
            metrics['functional_agent_seconds'] = _sum_known([m['timing']['agent_seconds'] for m in stage_metrics])
        else:
            for field,total,gate_value in (
                ('functional_input_tokens',tokens['input'],metrics['gate_input_tokens']),
                ('functional_output_tokens',tokens['output'],metrics['gate_output_tokens']),
                ('functional_agent_seconds',metrics['timing']['agent_seconds'],metrics['gate_agent_seconds'])):
                metrics[field] = total-gate_value if total is not None and gate_value is not None else None
    metrics['cumulative_agent_seconds'] = metrics['timing']['agent_seconds']
    metrics['cumulative_input_tokens'] = tokens['input']
    metrics['cumulative_output_tokens'] = tokens['output']
    metrics['final_pass_rate'] = checker_outcome.get('check_pass_rate') if checker_outcome else None
    metrics['stage_metrics'] = [{'path':str(p.relative_to(run)), 'skill_gate_status':m.get('skill_gate_status'),
                                  'skill_compliance':m.get('skill_compliance')} for p,m in zip(attempts,stage_metrics)]
    metrics['task_success'] = metadata.get('task_success')
    metrics['pairing_sha256'] = metadata['pairing_sha256']
    metrics['skill_usage'] = {'observed_read_skills':sorted({skill for m in stage_metrics
        for skill in (m.get('skill_compliance') or {}).get('observed_read_skills', [])}),
        'required_read_attempts':_sum_known([(m.get('skill_compliance') or {}).get('required_read_attempt_count') for m in stage_metrics]),
        'stage_count_with_trace':sum((p.parents[1]/'logs/aut/events.jsonl').is_file() for p in attempts),
        'certification':'consult_per_stage_evidence'}
    coverage_file = run/'evaluation/oracle_coverage.json'
    metrics['dns_property_checks'] = None
    if checker_outcome and coverage_file.exists():
        coverage = read_json(coverage_file)['checks']
        actual = {row['test_description']:row['passed'] for row in checker_test_rows(run/'results')}
        properties = {}
        for item in coverage:
            output_check = item['kind']=='client_resolver'
            prefix = 'Checking the output' if output_check else 'Checking the exit code'
            description = f"{prefix} of the command '{item['command']}' on '{item['device']}'"
            group = properties.setdefault(item['kind'],{'expected':0,'observed':0,'passed':0,'failed':0})
            group['expected'] += 1
            if description in actual:
                group['observed'] += 1
                group['passed'] += actual[description] is True
                group['failed'] += actual[description] is False
        for group in properties.values():
            group['pass_rate'] = group['passed']/group['observed'] if group['observed'] else None
            group['coverage_complete'] = group['observed']==group['expected']
        metrics['dns_property_checks'] = properties
    return metrics


def _replace_lab(source: Path, target: Path):
    # Solo copie derivate della run; nessuna directory sorgente condivisa.
    safe_path(target)
    staging = target.with_name(target.name+'.next')
    if staging.exists():
        shutil.rmtree(staging)
    copy_lab(source, staging)
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)


def _evaluate(config, spec, run, metadata, remaining):
    oracle = run/'evaluation/correction.yaml'
    if digest(oracle.read_bytes()) != metadata['correction_sha256']:
        raise ValueError('Snapshot correction alterato prima del checker')
    before = tree_hash(run/'lab')
    metadata.update(pipeline_state='CHECKER_RUNNING', checker_execution_success=None, task_success=None)
    write_json(run/'manifest.json', metadata)
    started = time.monotonic()
    try:
        outcome = run_checker(timed_config(config, min(spec.checker_timeout, max(1,math.floor(remaining)))), run, oracle)
        if (tree_hash(run/'lab') != before or digest(oracle.read_bytes()) != metadata['correction_sha256']
                or tree_hash(run/'input/lab') != metadata['input_lab_sha256']):
            raise RuntimeError('Checker ha alterato laboratorio o oracle')
        if time.monotonic()-started > remaining:
            raise TimeoutError('Budget totale superato nel checker (cleanup incluso)')
        metadata.update(checker_execution_success=True, task_success=outcome['task_success'], pipeline_state='COMPLETED')
        return outcome
    except BaseException:
        metadata.update(checker_execution_success=False, pipeline_state='CHECKER_FAILED', task_success=None)
        raise
    finally:
        metadata['checker_seconds'] = metadata.get('checker_seconds',0) + time.monotonic()-started


def execute(config, spec: Spec, cell: Cell, inventory: dict, preparation: dict, *, resume=False, rerun=False) -> Path:
    invocation_started = time.monotonic()
    action, run = plan(config,spec,cell,inventory,preparation,resume=resume,rerun=rerun)
    if action in ('SKIP','MISSING'):
        return run
    expected = conditions(config,spec,cell,inventory,preparation)
    sent = prompts(inventory,cell)
    if action == 'RUN':
        run.mkdir(parents=True,exist_ok=False)
        for name in ('logs/aut','results','evaluation','steps','input'):
            (run/name).mkdir(parents=True,exist_ok=True)
        copy_lab(spec.dataset/'lab', run/'input/lab')
        copy_lab(spec.dataset/'lab', run/'lab')
        content, sha = read_correction(spec.dataset/'correction.yaml')
        if sha != expected['correction_sha256']:
            raise ValueError('Oracle modificato durante allocazione')
        (run/'evaluation/correction.yaml').write_bytes(content)
        if expected.get('oracle_coverage_sha256'):
            shutil.copy2(spec.dataset/'oracle_coverage.json',run/'evaluation/oracle_coverage.json')
        (run/'input/prompt.md').write_text('\n\n'.join(sent))
        details = mode_details(cell.skill_mode)
        pairing = {k:v for k,v in expected.items() if k not in ('identity','prompts')}
        pairing.update(prompt_type=cell.prompt_type, repetition=cell.repetition)
        metadata = {'schema':'cost266_v1', 'run_id':cell.run_id, 'experiment_id':cell.experiment_id,
            'scenario_id':cell.scenario,'lab_id':cell.scenario,'dns_tree_id':cell.dns_tree,'task_level':'cost266',
            'prompt_type':cell.prompt_type,'strategy':cell.strategy,'skill_mode':cell.skill_mode,
            'repetition':cell.repetition,'run_number':cell.repetition,'replicate':cell.repetition,
            'agent':config.data['aut']['agent'], 'agent_version':config.data['aut']['version'],
            'model':config.model(),'model_server_version':None,'reasoning_effort':config.reasoning_effort(),
            'skill_protocol':expected['skill_protocol'], 'available_skills':list(details.available_skills),
            'forced_skills':list(details.forced_skills),'skill_bundle_sha256':expected['skill_bundles'],
            'execution_backend':('docker_sandbox' if config.data.get('docker_sandbox',{}).get('execution_backend')=='docker_sandbox'
                                 else config.data['aut']['agent']+'_cli'),
            'authentication':('sbx_oauth_proxy' if config.data.get('docker_sandbox',{}).get('execution_backend')=='docker_sandbox'
                              else ('local_chatgpt_login' if config.data['aut']['agent']=='codex' else 'local_google_login')),
            'api_key_used':False,
            'component_versions':component_versions(),'repository_revision':_revision(config.root),
            'conditions':expected,'conditions_sha256':fingerprint(expected),'pairing_sha256':fingerprint(pairing),
            'source_lab_sha256':expected['baseline_sha256'],'input_lab_sha256':expected['baseline_sha256'],
            'correction_sha256':expected['correction_sha256'],'prompt_sha256':fingerprint(expected['prompts']),
            'execution_mode':execution_mode(spec.protocol,cell.strategy),
            'requirements_sha256':fingerprint(stage_requirements(inventory)),
            'protocol_version':spec.protocol,'stage_count':len(sent),'active_seconds':0,'checker_seconds':0,'evaluation_revision':0,
            'started_at':utc_now(),'pipeline_state':'PENDING','aut_execution_success':None,
            'checker_execution_success':None,'task_success':None,'attempt_history':[]}
        for name,path in skill_paths(config,details.available_skills).items():
            prefix = 'dns_skill' if name == 'kathara-dns' else 'creation_skill'
            metadata[prefix+'_sha256'] = digest(path.read_bytes())
            metadata[prefix+'_bundle_sha256'] = tree_hash(path.parent)
        write_json(run/'manifest.json',metadata)
        completed = []
    else:
        metadata, completed = verify_run(run,expected)
    if rerun:
        revision = metadata['evaluation_revision']
        history = run/'evaluation/history'/f'revision_{revision:03d}'
        history.mkdir(parents=True,exist_ok=False)
        for file in ('manifest.json','evaluation/metrics.json','evaluation/correction.yaml'):
            if (run/file).exists():
                shutil.copy2(run/file,history/Path(file).name)
        shutil.copytree(run/'results', history/'results')
        shutil.rmtree(run/'results'); (run/'results').mkdir()
        metadata['evaluation_revision'] += 1
        metadata['last_reevaluated_at'] = utc_now()
    started = invocation_started
    previous_active = metadata.get('active_seconds',0)
    outcome = None
    def remaining():
        return spec.total_timeout - previous_active - (time.monotonic()-started)
    def execute_stages(continuous=None):
        for index in range(len(completed),len(sent)):
            if rerun:
                raise ValueError('Rivalutazione non può avviare AUT')
            if remaining() < 1:
                raise TimeoutError('Budget totale esaurito prima della fase AUT')
            step = run/'steps'/f'{index+1:02d}'
            attempts = step/'attempts'; attempts.mkdir(parents=True,exist_ok=True)
            number = max([int(p.name) for p in attempts.iterdir()],default=0)+1
            attempt = attempts/f'{number:03d}'; attempt.mkdir()
            for name in ('input','logs/aut','evaluation','results'):
                (attempt/name).mkdir(parents=True,exist_ok=True)
            source = run/'input/lab' if index == 0 else run/'steps'/f'{index:02d}'/'checkpoint'
            copy_lab(source,attempt/'input/lab')
            if continuous is None:
                copy_lab(source,attempt/'lab')
            initial = clean_lab(attempt/'input/lab')
            stage_id = cell.run_id + f'__stage{index+1:02d}__attempt{number:03d}'
            stage_metadata = {**metadata, 'run_id':stage_id,'parent_run_id':cell.run_id,'stage_index':index+1,
                'pipeline_state':'AUT_RUNNING','aut_execution_success':None,'aut_call_attempted':True,
                'prompt_sha256':digest(sent[index].encode()),'stage_started_at':utc_now()}
            (attempt/'input/prompt.md').write_text(sent[index])
            write_json(attempt/'manifest.json',stage_metadata)
            metadata.update(pipeline_state='AUT_RUNNING',pipeline_error=None)
            write_json(run/'manifest.json',metadata)
            stage_started = time.monotonic()
            try:
                timeout = min(spec.stage_timeout,max(1,math.floor(remaining())))
                if continuous is None:
                    run_aut(timed_config(config,timeout), SimpleNamespace(scenario_id='cost266'),
                            attempt,config.data['aut']['agent'],sent[index],skill_mode=cell.skill_mode,run_id=stage_id)
                else:
                    continuous.turn(attempt,stage_id,sent[index],index+1,timeout)
                if not (attempt/'logs/aut'/f'{stage_id}.eval').is_file():
                    raise RuntimeError('Log Inspect .eval mancante: fase non promossa a checkpoint')
                actual_prompt = (attempt/'logs/aut/prompt_sent.md').read_bytes()
                from ..skill_modes import execution_prompt
                from ..skill_gate import recovery_enabled
                expected_prompt = (sent[index] if recovery_enabled(config) and mode_details(cell.skill_mode).forced_skills
                                   else execution_prompt(cell.skill_mode,sent[index]))
                if config.data['aut']['agent']=='codex' and actual_prompt != expected_prompt.encode():
                    raise RuntimeError('Prompt effettivamente inviato diverso dal protocollo')
                if remaining() <= 0:
                    raise TimeoutError('Budget totale superato dopo AUT (cleanup incluso)')
                if tree_hash(attempt/'input/lab') != manifest_hash(initial):
                    raise RuntimeError('Input fase alterato')
                invariant_checks(run/'input/lab',attempt/'lab',inventory)
                after = clean_lab(attempt/'lab')
                write_json(attempt/'logs/diff.json',manifest_changes(initial,after))
                phase = 6 if cell.strategy == 'one_shot' else index+1
                static_started = time.monotonic()
                validation = static_validation(attempt/'lab',inventory,phase)
                previous_checks = completed[-1]['static_checks'] if completed else {}
                validation['regressions'] = [key for key,passed in previous_checks.items() if passed and not validation['checks'].get(key)]
                stage_metadata['static_validation_seconds'] = time.monotonic()-static_started
                stage_metadata['static_regressions'] = validation['regressions']
                write_json(attempt/'evaluation/static.json',validation)
                copy_lab(attempt/'lab',step/'checkpoint')
                stage_metadata['checkpoint_sha256'] = tree_hash(step/'checkpoint')
                stage_metadata['checkpoint_bytes'] = sum(p.stat().st_size for p in (step/'checkpoint').rglob('*') if p.is_file())
                stage_metadata.update(pipeline_state='COMPLETED',aut_execution_success=True,stage_completed=True)
            except BaseException as exc:
                stage_metadata.update(pipeline_state='AUT_FAILED',aut_execution_success=False,pipeline_error=f'{type(exc).__name__}: {exc}')
                raise
            finally:
                if continuous is not None:
                    stage_metadata.update(continuous.stage_state)
                    stage_metadata['stage_completed'] = stage_metadata['pipeline_state']=='COMPLETED'
                stage_metadata['stage_wall_seconds'] = time.monotonic()-stage_started
                prompt_file = attempt/'logs/aut/prompt_sent.md'
                stage_metadata['prompt_sent_sha256'] = digest(prompt_file.read_bytes()) if prompt_file.exists() else None
                write_json(attempt/'manifest.json',stage_metadata)
                metrics = make_metrics(attempt,stage_metadata,total_seconds=stage_metadata['stage_wall_seconds'],checker_seconds=None,checker_outcome=None)
                metrics.update(aut_call_attempted=True,stage_index=index+1,attempt=number)
                for field in ('thread_id','sandbox_id','sandbox_name','session_count','sandbox_count',
                              'context_continuity_verified','stage_completed','stage_prompt_sha256'):
                    if field in stage_metadata: metrics[field]=stage_metadata[field]
                for field in ('checkpoint_sha256','checkpoint_bytes'):
                    metrics[field] = stage_metadata.get(field)
                metrics.update(static_validation_seconds=stage_metadata.get('static_validation_seconds'),
                               static_regressions=stage_metadata.get('static_regressions'))
                invocation = read_json(attempt/'logs/aut/invocation.json') if (attempt/'logs/aut/invocation.json').is_file() else {}
                events = attempt/'logs/aut/events.jsonl'
                metrics['aut_call_observed'] = bool(invocation.get('command') or (events.is_file() and events.read_bytes().strip()))
                write_json(attempt/'evaluation/metrics.json',metrics)
                receipt = {'input_sha256':manifest_hash(initial), 'artifacts': {
                    str(p.relative_to(attempt)):digest(p.read_bytes()) for p in attempt.rglob('*') if p.is_file()
                    and ('logs' in p.relative_to(attempt).parts or 'evaluation' in p.relative_to(attempt).parts or p.name=='manifest.json')}}
                write_json(attempt/'receipt.json',receipt)
                metadata['attempt_history'].append({'receipt':str((attempt/'receipt.json').relative_to(run)),
                                                    'sha256':digest((attempt/'receipt.json').read_bytes())})
                metadata['active_seconds'] = previous_active + time.monotonic()-started
                write_json(run/'manifest.json',metadata)
            artifacts = {str(p.relative_to(attempt)):digest(p.read_bytes()) for p in attempt.rglob('*') if p.is_file()
                         and ('logs' in p.relative_to(attempt).parts or 'evaluation' in p.relative_to(attempt).parts or p.name=='manifest.json')}
            record = {'input_sha256':manifest_hash(initial),'checkpoint_sha256':tree_hash(step/'checkpoint'),
                'prompt_sha256':expected['prompts'][index],'attempt':str(attempt.relative_to(step)),
                'artifacts':artifacts,'static_checks':validation['checks'],
                'checkpoint_bytes':sum(p.stat().st_size for p in (step/'checkpoint').rglob('*') if p.is_file())}
            write_json(step/'completed.json',record)
            completed.append(record)
            _replace_lab(step/'checkpoint',run/'lab')
            metadata['completed_stages'] = len(completed)
            write_json(run/'manifest.json',metadata)
    continuous = None
    try:
        if spec.protocol == CONTINUOUS_VERSION and cell.strategy == 'incremental' and not rerun and len(completed)<len(sent):
            from .continuous import ContinuousAutSession
            def turn_timeout():
                if remaining()<1:
                    raise TimeoutError('Budget totale esaurito nel gate')
                return min(spec.stage_timeout,max(1,math.floor(remaining())))
            continuous = ContinuousAutSession(config,run,cell.skill_mode,turn_timeout)
            continuous.run_all(execute_stages)
            if any(e['cleanup_ok'] is not True for e in continuous.environments):
                raise RuntimeError('Cleanup della sessione continua non verificato')
        elif len(completed)<len(sent):
            execute_stages()
        metadata.update(aut_execution_success=True,pipeline_state='AUT_COMPLETED',final_lab_sha256=tree_hash(run/'lab'))
        if remaining() < 1 and not rerun:
            raise TimeoutError('Budget totale esaurito prima del checker finale')
        # Rivalutazione ha un budget checker esplicito e non riapre il budget AUT.
        outcome = _evaluate(config,spec,run,metadata,spec.checker_timeout if rerun else remaining())
    except BaseException as exc:
        if metadata['pipeline_state'] != 'CHECKER_FAILED':
            metadata.update(pipeline_state='INCOMPLETE',aut_execution_success=len(completed)==len(sent))
        metadata['pipeline_error'] = f'{type(exc).__name__}: {exc}'
        metadata['task_success'] = None
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):
            raise
    finally:
        if continuous is not None:
            session_record = read_json(run/'logs/aut/continuous_session.json')
            metadata.update({key:session_record.get(key) for key in (
                'sandbox_name','sandbox_id','thread_id','session_count','sandbox_count',
                'writable_sandbox_count','protected_sandbox_count','context_continuity_verified')})
            metadata['session_cleanup_ok'] = session_record.get('cleanup_ok')
        metadata['active_seconds'] = previous_active + time.monotonic()-started
        metadata['completed_at'] = utc_now()
        if tree_hash(spec.dataset/'lab') != expected['baseline_sha256']:
            metadata.update(pipeline_state='INCOMPLETE',task_success=None,pipeline_error='Baseline sorgente alterata')
        write_json(run/'manifest.json',metadata)
        changes = manifest_changes(manifest(run/'input/lab'),manifest(run/'lab'))
        write_json(run/'logs/diff.json',changes)
        metrics = collect_metrics(run,metadata,checker_outcome=outcome)
        metrics['file_changes'] = changes
        metadata['active_seconds'] = previous_active + time.monotonic()-started
        metrics['timing']['total_seconds'] = metadata['active_seconds']
        write_json(run/'evaluation/metrics.json',metrics)
        write_json(run/'manifest.json',metadata)
    return run
