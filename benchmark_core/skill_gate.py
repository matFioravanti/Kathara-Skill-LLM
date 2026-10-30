"""Fail-closed Skill Gate selection, evidence checks and recovery_v1 lifecycle.

The legacy strict policy remains blocked. The recovery policy uses the verified
external sbx mount/identity boundary, never a shell-only read-only flag.
"""
from pathlib import Path
import json

from .aut_observation import observe
from .skill_modes import mode_details
from .workspace import utc_now, write_json

PROTOCOL = 'enforced_read_v1'
RECOVERY_POLICY = 'recovery_v1'
RECOVERY_FIELDS = ('skill_gate_load_methods', 'skill_gate_read_attempts',
    'skill_gate_retry_count', 'skill_gate_fallback_used', 'skill_gate_fallback_skills',
    'skill_gate_fallback_sha256_verified', 'skill_gate_context_delivery_verified',
    'skill_gate_initial_read_seconds', 'skill_gate_retry_seconds', 'skill_gate_fallback_seconds',
    'skill_gate_initial_input_tokens', 'skill_gate_initial_output_tokens',
    'skill_gate_retry_input_tokens', 'skill_gate_retry_output_tokens',
    'skill_gate_fallback_input_tokens', 'skill_gate_fallback_output_tokens',
    'skill_gate_recovery_policy_version', 'skill_gate_session_id', 'skill_gate_session_count')
FIELDS = ('skill_gate_enabled', 'skill_gate_status', 'skill_gate_required_skills',
          'skill_gate_verified_skills', 'skill_gate_read_seconds',
          'skill_gate_verification_seconds', 'skill_gate_blocked',
          'skill_gate_write_attempts_blocked', 'skill_gate_backend_enforcement',
          'skill_gate_input_tokens', 'skill_gate_output_tokens',
          'skill_gate_write_seconds', 'skill_gate_total_seconds',
          'write_phase_input_tokens', 'write_phase_output_tokens',
          'skill_gate_isolation_verified', 'skill_gate_isolation_violations',
          'skill_gate_context_strategy', 'skill_gate_backend',
          'skill_gate_protocol_version', 'skill_gate_state_history',
          'skill_gate_certification', 'skill_gate_context_continuity_verified') + RECOVERY_FIELDS


class SkillGateError(RuntimeError):
    """A required gate was blocked; the writable phase must not be run."""


def configured_protocol(config):
    value = config.data.get('aut', {}).get('skill_protocol', 'explicit_read_v2')
    if value not in ('explicit_read_v2', PROTOCOL):
        raise ValueError(f'Protocollo Skill non supportato: {value!r}')
    return value


def gate_record(required, backend):
    return {'skill_gate_enabled': bool(required),
            'skill_gate_status': 'unsupported_backend' if required else 'not_required',
            'skill_gate_required_skills': list(required), 'skill_gate_verified_skills': [],
            'skill_gate_read_seconds': None, 'skill_gate_verification_seconds': None,
            'skill_gate_blocked': bool(required), 'skill_gate_write_attempts_blocked': None,
            'skill_gate_backend_enforcement': f'{backend}:unverified' if required else None,
            'skill_gate_input_tokens': None, 'skill_gate_output_tokens': None,
            'skill_gate_write_seconds': None, 'skill_gate_total_seconds': None,
            'write_phase_input_tokens': None, 'write_phase_output_tokens': None,
            'skill_gate_isolation_verified': None, 'skill_gate_isolation_violations': None,
            'skill_gate_context_strategy': None, 'skill_gate_backend': backend,
            'skill_gate_protocol_version': PROTOCOL,
            'skill_gate_certification': 'NOT_RUN',
            'skill_gate_context_continuity_verified': None,
            'skill_gate_state_history': [{'status': 'unsupported_backend' if required else 'not_required', 'timestamp': utc_now()}]}


def enforce_or_block(config, run: Path, agent: str, mode: str):
    """Reject unsupported policies/backends before AUT startup."""
    if configured_protocol(config) != PROTOCOL:
        return
    if agent != 'codex':
        raise SkillGateError('unsupported_backend: enforced_read_v1 supports Codex only')
    required = mode_details(mode).forced_skills
    backend = ('docker_sandbox' if config.data.get('docker_sandbox', {}).get('execution_backend') == 'docker_sandbox' else 'codex_cli')
    record = gate_record(required, backend)
    supported = bool(required) and backend == 'docker_sandbox' and recovery_enabled(config)
    if supported:
        record['skill_gate_status'] = 'pending'
        record['skill_gate_recovery_policy_version'] = RECOVERY_POLICY
        record['skill_gate_state_history'] = [{'status': 'pending', 'timestamp': utc_now()}]
    logs = run / 'logs/aut'
    logs.mkdir(parents=True, exist_ok=True)
    write_json(logs / 'skill_gate.json', record)
    if required:
        if supported:
            return
        raise SkillGateError(f'unsupported_backend: {backend} has no verified protected read phase')


def recovery_enabled(config):
    policy = config.data.get('aut', {}).get('skill_gate_recovery_policy')
    if policy not in (None, RECOVERY_POLICY):
        raise ValueError(f'Unsupported recovery policy: {policy!r}')
    retries = config.data.get('aut', {}).get('skill_gate_max_retries', 2)
    if type(retries) is not int or not 0 <= retries <= 10:
        raise ValueError('aut.skill_gate_max_retries must be an integer between 0 and 10')
    return configured_protocol(config) == PROTOCOL and policy == RECOVERY_POLICY


def evaluate_read_evidence(run: Path, metadata: dict, events: list[dict], *, returncode: int | None, timed_out: bool, phase='A', evidence_dir=None):
    """Evaluate saved phase-A evidence; this function alone never opens the gate.

    The caller must independently verify isolation, trace provenance, continuity
    and lifecycle management before using this result to open the gate.
    """
    required = list(mode_details(metadata['skill_mode']).forced_skills)
    if not required:
        return {'status': 'not_required', 'verified_skills': [], 'blocked': False}
    if phase != 'A':
        return {'status': 'invalid_evidence_phase', 'verified_skills': [], 'blocked': True}
    # Once phase-separated artifacts exist, never fall back to the historical
    # aggregate stream, which can contain reads performed after gate opening.
    phase_root = run / 'logs/aut/phase_a'
    if evidence_dir is not None:
        import re
        relative = Path(evidence_dir)
        if relative.as_posix() != 'phase_a' and not re.fullmatch(r'retries/attempt_\d{2}', relative.as_posix()):
            return {'status': 'invalid_evidence_phase', 'verified_skills': [], 'blocked': True}
        phase_root = run / 'logs/aut' / relative
    trace_path = phase_root / 'events.jsonl'
    if (metadata.get('skill_protocol') == PROTOCOL or phase_root.exists()
            or (run / 'logs/aut/phase_b').exists()):
        try:
            saved = [json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        except (OSError, ValueError):
            return {'status': 'invalid_phase_a_artifact', 'verified_skills': [], 'blocked': True}
        if saved != events:
            return {'status': 'phase_a_evidence_mismatch', 'verified_skills': [], 'blocked': True}
    else:
        trace_path = run / 'logs/aut/events.jsonl'
    if timed_out:
        return {'status': 'read_phase_timeout', 'verified_skills': [], 'blocked': True}
    if (returncode != 0 or not any(e.get('type') == 'turn.completed' for e in events)
            or any(e.get('type') in ('turn.failed', 'error') for e in events)):
        return {'status': 'read_phase_failed', 'verified_skills': [], 'blocked': True}
    # A shell read with no exit code is not proof of a successful read.
    # Preserve its started event for traceability but exclude its incomplete result.
    safe_events = []
    for event in events:
        item = event.get('item') if isinstance(event.get('item'), dict) else {}
        if (item.get('type') == 'command_execution' and event.get('type') == 'item.completed'
                and (type(item.get('exit_code')) is not int or item['exit_code'] != 0)):
            continue
        if item.get('type') == 'file_change' and event.get('type') == 'item.completed' and item.get('status') == 'completed':
            return {'status': 'isolation_violation', 'verified_skills': [], 'blocked': True}
        safe_events.append(event)
    _, compliance = observe(run, metadata, safe_events, trace_path=trace_path)
    details = compliance['skill_details']
    verified = [s for s in required if details[s]['complete_read_verified'] is True and details[s]['dedicated_read'] is True]
    return {'status': 'evidence_verified' if len(verified) == len(required) else 'verification_failed',
            'verified_skills': verified, 'blocked': len(verified) != len(required)}


def certification_outcome(checks):
    """Classify observed checks only: None means NOT_RUN, False means failure.

    Reading verifies returned bytes, never understanding or correct application.
    No backend is enabled by this reporting function.
    """
    required = ('isolation', 'read', 'continuity', 'phase_b')
    values = [checks.get(key) for key in required]
    if any(value is not None and type(value) is not bool for value in values):
        raise ValueError('Certification checks must be bool or None')
    if any(value is False for value in values):
        return 'FAILED'
    if all(value is True for value in values):
        return 'CERTIFIED'
    if any(value is True for value in values):
        return 'PARTIALLY_VERIFIED'
    return 'NOT_RUN'


def read_gate_metrics(run: Path):
    try:
        data = json.loads((run / 'logs/aut/skill_gate.json').read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {field: data.get(field) for field in FIELDS}
    except (OSError, ValueError):
        pass
    return {field: None for field in FIELDS}


def run_recovery_gate(*, config, run, workspace, original_prompt, mode, session_factory=None):
    """Ordinary-run recovery_v1 orchestration; only missing reads trigger recovery.

    Technical, isolation, integrity and continuity errors always fail closed.
    Fallback proves delivery of exact input bytes, never autonomous reading.
    """
    import hashlib
    import tempfile
    import time
    from .skill_modes import source_paths, SKILL_CONFIG_KEYS
    from .workspace import tree_hash
    from .docker_sandbox_runner import ProtectedCodexSession
    if not recovery_enabled(config) or config.data.get('docker_sandbox',{}).get('execution_backend')!='docker_sandbox':
        raise SkillGateError('unsupported_backend: recovery_v1 requires Docker Sandbox')
    required=list(mode_details(mode).forced_skills)
    if not required:
        raise ValueError('Recovery must not run for optional skill modes')
    logs=run/'logs/aut'; logs.mkdir(parents=True,exist_ok=True)
    record=gate_record(required,'docker_sandbox')
    record.update({field:None for field in RECOVERY_FIELDS})
    record.update(skill_gate_recovery_policy_version=RECOVERY_POLICY, skill_gate_load_methods={},
                  skill_gate_read_attempts=0,skill_gate_retry_count=0,skill_gate_fallback_used=False,
                  skill_gate_fallback_skills=[],skill_gate_verification_seconds=0.0,
                  skill_gate_retry_seconds=0.0,skill_gate_fallback_seconds=0.0,
                  skill_gate_context_strategy='explicit_resume_shared_state',skill_gate_blocked=True)
    record['skill_gate_state_history']=[]
    started=time.monotonic(); verification=0.0; session=None
    def state(value):
        record['skill_gate_status']=value
        record['skill_gate_state_history'].append({'status':value,'timestamp':utc_now()})
        write_json(logs/'skill_gate.json',record)
    def verify_baseline():
        if tree_hash(workspace)!=baseline:
            record['skill_gate_isolation_violations']=1
            record['skill_gate_isolation_verified']=False
            raise SkillGateError('isolation_violation: protected baseline changed')
        for skill, source in sources.items():
            if source.read_bytes()!=contents[skill]:
                raise SkillGateError('skill_hash_mismatch: canonical source changed: '+skill)
    def turn(directory,prompt):
        events,result=session.turn(prompt=prompt,directory=logs/directory,
                                   timeout=config.data['benchmark']['timeout_seconds'])
        record['skill_gate_session_id']=session.thread_id; record['skill_gate_session_count']=1
        record['skill_gate_context_continuity_verified']=True
        return events,result
    def read_prompt(missing,retry=False):
        intro=('La lettura delle seguenti Skill non risulta verificata. Ripeti soltanto queste letture.\n' if retry else
               'Prima di configurare il laboratorio, leggi integralmente le seguenti Skill.\n')
        return (intro+'\n'.join(f'- `.codex/skills/{s}/SKILL.md`' for s in missing)+
                '\nUsa una operazione di lettura dedicata per ciascun file. Se lungo, leggilo in blocchi consecutivi fino alla fine. '
                'Usa `cat .codex/skills/NOME/SKILL.md` in un comando separato per ciascuna Skill. '
                'Non concatenare wc, inventario, echo o altri comandi alla lettura. '
                'Il laboratorio rimane protetto. Non modificare file e non configurare il laboratorio. Termina dopo la lettura.').encode('utf-8')
    try:
        state('preparing')
        metadata=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        metadata={**metadata,'agent':'codex','skill_mode':mode,'skill_protocol':PROTOCOL}
        sources=source_paths(config,tuple(required)); contents={}
        for skill,path in sources.items():
            raw=path.read_bytes(); expected=metadata.get(SKILL_CONFIG_KEYS[skill]+'_sha256')
            staged=(workspace/'.codex/skills'/skill/'SKILL.md').read_bytes()
            if not expected or hashlib.sha256(raw).hexdigest()!=expected or staged!=raw:
                raise SkillGateError('skill_hash_mismatch: '+skill)
            raw.decode('utf-8')  # No lossy decoding or newline normalization.
            contents[skill]=raw
        baseline=tree_hash(workspace)
        record['baseline_sha256']=baseline
        with tempfile.TemporaryDirectory(prefix='kathara-gate-state-',dir=workspace.parent) as temporary:
            # The parent is never exported; only this separate state directory.
            session=(session_factory or ProtectedCodexSession)(workspace=workspace,state=Path(temporary),logs=logs,config=config)
            try:
                session.create(readonly=True)
                record['skill_gate_isolation_verified']=True
                record['skill_gate_isolation_violations']=0
                record['skill_gate_backend_enforcement']='docker_sandbox:ro_nonroot_zero_caps_no_mcp'
                max_retries=config.data['aut'].get('skill_gate_max_retries',2)
                for attempt in range(1+max_retries):
                    missing=[s for s in required if s not in record['skill_gate_load_methods']]
                    if not missing: break
                    directory='phase_a' if attempt==0 else f'retries/attempt_{attempt:02d}'
                    state('initial_read' if attempt==0 else 'retry_read')
                    record['skill_gate_read_attempts']+=1
                    if attempt: record['skill_gate_retry_count']+=1
                    events,result=turn(directory,read_prompt(missing,retry=attempt>0))
                    key='skill_gate_initial_read_seconds' if attempt==0 else 'skill_gate_retry_seconds'
                    record[key]=(record[key] or 0)+result['duration_seconds']
                    check_start=time.monotonic(); verify_baseline()
                    verdict=evaluate_read_evidence(run,metadata,events,returncode=result['returncode'],timed_out=result['timed_out'],evidence_dir=directory)
                    if verdict['status'] not in ('evidence_verified','verification_failed'):
                        raise SkillGateError(verdict['status'])
                    for skill in verdict['verified_skills']:
                        record['skill_gate_load_methods'].setdefault(skill,'read_verified' if attempt==0 else 'retry_verified')
                    verification+=time.monotonic()-check_start
                    record['skill_gate_verified_skills']=[s for s in required if s in record['skill_gate_load_methods']]
                    write_json(logs/'skill_gate.json',record)
                missing=[s for s in required if s not in record['skill_gate_load_methods']]
                if missing:
                    state('fallback_loading'); check_start=time.monotonic(); verify_baseline()
                    payload=b'CARICAMENTO DETERMINISTICO DELLE SKILL MANCANTI\nLe sezioni seguenti contengono le istruzioni integrali delle Skill, non il prompt funzionale. Non modificare file. Conferma la ricezione e attendi.\n'
                    for skill in missing:
                        raw=sources[skill].read_bytes()
                        if raw!=contents[skill] or hashlib.sha256(raw).hexdigest()!=metadata[SKILL_CONFIG_KEYS[skill]+'_sha256']:
                            record['skill_gate_fallback_sha256_verified']=False
                            raise SkillGateError('fallback_hash_mismatch: '+skill)
                        payload+=b'\nBEGIN SKILL '+skill.encode()+b'\n'+raw+b'\nEND SKILL '+skill.encode()+b'\n'
                    record['skill_gate_fallback_used']=True; record['skill_gate_fallback_skills']=missing
                    record['skill_gate_fallback_sha256_verified']=True
                    verification+=time.monotonic()-check_start
                    events,result=turn('fallback',payload)
                    check_start=time.monotonic(); verify_baseline()
                    saved=(logs/'fallback/prompt_sent.md').read_bytes()
                    if saved!=payload or not all(contents[s] in saved for s in missing) or result.get('stdin_delivery_verified') is not True:
                        record['skill_gate_context_delivery_verified']=False
                        raise SkillGateError('fallback_delivery_incomplete')
                    for skill in missing: record['skill_gate_load_methods'][skill]='preloaded_fallback'
                    record['skill_gate_fallback_seconds']=result['duration_seconds']
                    verification+=time.monotonic()-check_start
                check_start=time.monotonic(); verify_baseline()
                if set(record['skill_gate_load_methods'])!=set(required):
                    raise SkillGateError('Required content not delivered')
                record['skill_gate_verified_skills']=required
                record['skill_gate_context_delivery_verified']=True
                verification+=time.monotonic()-check_start
                state('passed')
                # Never overlap the protected environment and the writable one.
                session.close(); verify_baseline()
                session.create(readonly=False)
                record['skill_gate_blocked']=False
                state('write_phase_running')
                _,result=turn('phase_b',original_prompt.encode('utf-8'))
                record['skill_gate_write_seconds']=result['duration_seconds']
                state('completed')
            finally:
                session.close()
    except BaseException as e:
        record['error']=f'{type(e).__name__}: {e}'
        if record['skill_gate_status']!='write_phase_running': record['skill_gate_blocked']=True
        # A technical error is distinct from missing spontaneous reading.
        state('technical_error')
        raise
    finally:
        record['skill_gate_total_seconds']=time.monotonic()-started
        record['skill_gate_verification_seconds']=verification
        turns=session.turns if session else []
        initial=[r for p,r in turns if p.name=='phase_a']
        retries=[r for p,r in turns if p.parent.name=='retries']
        fallback=[r for p,r in turns if p.name=='fallback']
        writable=[r for p,r in turns if p.name=='phase_b']
        record['skill_gate_initial_read_seconds']=sum(r['duration_seconds'] for r in initial) if initial else None
        record['skill_gate_retry_seconds']=sum(r['duration_seconds'] for r in retries) if retries else None
        record['skill_gate_fallback_seconds']=sum(r['duration_seconds'] for r in fallback) if fallback else None
        record['skill_gate_write_seconds']=sum(r['duration_seconds'] for r in writable) if writable else None
        def sum_usage(items,key):
            values=[result.get('usage',{}).get(key) if isinstance(result.get('usage'),dict) else None for _,result in items]
            return sum(values) if values and all(type(v) is int for v in values) else None
        for name,parts in [('initial',[t for t in turns if t[0].name=='phase_a']),
                           ('retry',[t for t in turns if t[0].parent.name=='retries']),
                           ('fallback',[t for t in turns if t[0].name=='fallback'])]:
            for kind in ('input','output'):
                record[f'skill_gate_{name}_{kind}_tokens']=sum_usage(parts,kind+'_tokens')
        protected=[t for t in turns if t[0].name!='phase_b']
        writable=[t for t in turns if t[0].name=='phase_b']
        for kind in ('input','output'):
            record[f'skill_gate_{kind}_tokens']=sum_usage(protected,kind+'_tokens')
            record[f'write_phase_{kind}_tokens']=sum_usage(writable,kind+'_tokens')
        record['skill_gate_read_seconds']=sum(r['duration_seconds'] for p,r in turns if p.name=='phase_a' or p.parent.name=='retries') if turns else None
        # Include failed partial turns in the compatibility trace too.
        aggregate_events=[]
        for path,result in turns:
            for line in (path/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                try:
                    event=json.loads(line)
                    phase=str(path.relative_to(logs))
                    event['_skill_gate_phase']=phase
                    # Codex restarts item numbering on every resumed turn.
                    # Keep raw phase logs unchanged; namespace compatibility IDs
                    # so Inspect/observation cannot overwrite earlier tools.
                    if isinstance(event.get('item'),dict) and event['item'].get('id'):
                        event['item']={**event['item'],'id':phase+':'+event['item']['id']}
                    aggregate_events.append(event)
                except (ValueError,TypeError): pass
        (logs/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in aggregate_events),encoding='utf-8')
        (logs/'stderr.log').write_bytes(b'\n'.join((p/'stderr.log').read_bytes() for p,_ in turns))
        from .sampling_telemetry import load_sampling_telemetry, merge_sampling_telemetries, save_sampling_telemetry
        telemetry_cfg = config.sampling_telemetry_config()
        if telemetry_cfg.get('enabled') and telemetry_cfg.get('mode') == 'http_trace':
            phase_samples = [sample for path,_ in turns
                             if (sample := load_sampling_telemetry(path)) is not None]
            save_sampling_telemetry(logs, merge_sampling_telemetries(phase_samples))
        (logs/'prompt_sent.md').write_bytes(original_prompt.encode('utf-8'))
        usage={k:sum_usage(turns,k) for k in ('input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens','cache_write_input_tokens')}
        write_json(logs/'result.json',{'returncode':0 if record['skill_gate_status']=='completed' else 1,
            'timed_out':any(r.get('timed_out') for _,r in turns),
            'duration_seconds':sum(r['duration_seconds'] for _,r in turns) if turns else None,
            'sandbox_overhead_seconds':session.overhead if session else None,
            'usage':usage,'final_message':turns[-1][1].get('final_message') if turns else None,'error':record.get('error')})
        write_json(logs/'invocation.json',{'execution_backend':'docker_sandbox','skill_protocol':PROTOCOL,
            'skill_gate_recovery_policy_version':RECOVERY_POLICY,'authentication':'sbx_oauth_proxy',
            'model':config.model(),'reasoning_effort':config.reasoning_effort(),'commands':session.commands if session else []})
        write_json(logs/'sandbox_metadata.json',{'execution_backend':'docker_sandbox',
            'codex_sandbox_version':session.version if session else None,
            'cleanup_ok':all(c['ok'] for c in session.cleanup) if session and session.cleanup else None,
            'environments':session.cleanup if session else [],'error':record.get('error')})
        record['skill_gate_certification']=('FAILED' if record.get('error') else
            certification_outcome({'isolation':record['skill_gate_isolation_verified'],
                'read':record['skill_gate_context_delivery_verified'],
                'continuity':record['skill_gate_context_continuity_verified'],
                'phase_b':True if record['skill_gate_status']=='completed' else None}))
        write_json(logs/'skill_gate.json',record)
