"""Metriche normalizzate della run, derivate da trace e risultati conservati."""
from pathlib import Path
from datetime import datetime
import hashlib
import json

from .checker_runner import checker_test_rows, parse_reports



def load_jsonl(path: Path) -> list[dict]:
    events = []
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def codex_usage(events: list[dict]) -> dict:
    """Il runner supporta turn.completed.usage; l'ultimo usage è il totale finale.

    Rende coerente il conteggio dei token tra JSON, CSV, Excel e Inspect:
    - Distingue il totale riportato dal modello da quello calcolato
    - Non duplica i reasoning token (i reasoning token sono già un sottoinsieme di output_tokens)
    """
    final_usage = None
    for event in events:
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            final_usage = event["usage"]
    if final_usage is None:
        return {
            "input": None, "cached_input": None, "output": None,
            "reasoning": None, "total": None, "total_reported": None,
            "total_calculated": None, "cache_write_input": None,
        }
    input_tokens = _token_value(final_usage.get("input_tokens"))
    cached_input = _token_value(final_usage.get("cached_input_tokens"))
    output_tokens = _token_value(final_usage.get("output_tokens"))
    reasoning_tokens = _token_value(final_usage.get("reasoning_output_tokens"))
    total_reported = _token_value(final_usage.get("total_tokens"))
    cache_write = _token_value(final_usage.get("cache_write_input_tokens"))
    total_calculated = (
        input_tokens + output_tokens
        if (input_tokens is not None and output_tokens is not None)
        else None
    )
    total = total_reported if total_reported is not None else total_calculated
    return {
        "input": input_tokens,
        "cached_input": cached_input,
        "output": output_tokens,
        "reasoning": reasoning_tokens,
        "total": total,
        "total_reported": total_reported,
        "total_calculated": total_calculated,
        "cache_write_input": cache_write,
    }


def antigravity_usage(events: list[dict]) -> dict:
    final_usage = None
    for event in events:
        if event.get("event") == "result" and isinstance(event.get("result"), dict):
            usage = event["result"].get("usage")
            if isinstance(usage, dict):
                final_usage = usage
    if final_usage is None:
        return codex_usage([])
    input_tokens = _token_value(final_usage.get("input_tokens"))
    cached_input = _token_value(final_usage.get("cache_read_tokens"))
    output_tokens = _token_value(final_usage.get("output_tokens"))
    reasoning_tokens = _token_value(final_usage.get("thinking_tokens"))
    total_reported = _token_value(final_usage.get("total_tokens"))
    cache_write = _token_value(final_usage.get("cache_write_tokens"))
    total_calculated = (
        input_tokens + output_tokens
        if (input_tokens is not None and output_tokens is not None)
        else None
    )
    total = total_reported if total_reported is not None else total_calculated
    return {
        "input": input_tokens,
        "cached_input": cached_input,
        "output": output_tokens,
        "reasoning": reasoning_tokens,
        "total": total,
        "total_reported": total_reported,
        "total_calculated": total_calculated,
        "cache_write_input": cache_write,
    }


def _token_value(value):
    return value if type(value) is int and value >= 0 else None




def _checker_summary(run: Path, outcome: dict | None) -> dict:
    if outcome is None:
        try:
            outcome, _ = parse_reports(run / "results")
        except Exception:
            try:
                partial = checker_test_rows(run / "results")
            except (OSError, ValueError, UnicodeError):
                partial = []
            passed = sum(row["passed"] for row in partial)
            failed = len(partial) - passed
            return {
                "passed": passed if partial else None,
                "failed": failed if partial else None,
                "total": len(partial) if partial else None,
                "pass_rate": passed / len(partial) if partial else None,
            }
    return {
        "passed": outcome.get("checks_passed"),
        "failed": outcome.get("checks_failed"),
        "total": outcome.get("checks_total"),
        "pass_rate": outcome.get("check_pass_rate"),
    }


def _duration(path: Path, key: str) -> float | None:
    try:
        value = json.loads(path.read_text()).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _sandbox_meta(logs: Path) -> dict:
    """Legge sandbox_metadata.json se presente; restituisce dict vuoto altrimenti."""
    path = logs / "sandbox_metadata.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _sampling_meta(run: Path) -> dict | None:
    """Legge la telemetria di campionamento da logs/aut/sampling_telemetry.json o metrics.json precedente."""
    telemetry_file = run / "logs/aut/sampling_telemetry.json"
    if telemetry_file.is_file():
        try:
            data = json.loads(telemetry_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    prev_metrics_file = run / "evaluation/metrics.json"
    if prev_metrics_file.is_file():
        try:
            prev_data = json.loads(prev_metrics_file.read_text(encoding="utf-8"))
            if isinstance(prev_data, dict) and isinstance(prev_data.get("llm_sampling"), dict):
                return prev_data["llm_sampling"]
        except (OSError, ValueError):
            pass
    return None


def _recovery_delivery_metrics(run: Path, metadata: dict, gate: dict, compliance: dict) -> dict:
    """Reconcile recovery delivery with protected evidence, never phase-B reads.

    Unknown or contradictory evidence remains unknown. The gate's certification
    string alone cannot establish either reading or delivery.
    """
    from .skill_gate import evaluate_read_evidence
    from .skill_modes import mode_details

    unknown = {'skill_autonomous_read_before_write': None,
               'skill_delivery_before_write': None, 'skill_delivery_details': None}
    if (metadata.get('agent') != 'codex' or metadata.get('skill_protocol') != 'enforced_read_v1'
            or gate.get('skill_gate_recovery_policy_version') != 'recovery_v1'):
        return unknown
    try:
        required = list(mode_details(metadata['skill_mode']).forced_skills)
    except (KeyError, ValueError):
        return unknown
    if not required or gate.get('skill_gate_enabled') is not True:
        return unknown
    methods = gate.get('skill_gate_load_methods')
    methods = methods if isinstance(methods, dict) else {}
    details = {skill: {'method': methods.get(skill), 'autonomous_read_before_write': None,
                       'delivery_before_write': None} for skill in required}
    result = {**unknown, 'skill_delivery_details': details}
    history = gate.get('skill_gate_state_history')
    if not isinstance(history, list) or not all(isinstance(entry, dict) for entry in history):
        return result
    states = [entry.get('status') for entry in history]
    try:
        passed_at, write_at = states.index('passed'), states.index('write_phase_running')
        passed_time = datetime.fromisoformat(history[passed_at]['timestamp'])
        write_time = datetime.fromisoformat(history[write_at]['timestamp'])
        ordered = (passed_at < write_at and passed_time.utcoffset() is not None
                   and write_time.utcoffset() is not None and passed_time <= write_time)
    except (ValueError, TypeError, KeyError, IndexError):
        ordered = False
    session = gate.get('skill_gate_session_id')
    if (not ordered or gate.get('skill_gate_status') not in ('write_phase_running', 'completed', 'technical_error')
            or gate.get('skill_gate_protocol_version') != 'enforced_read_v1'
            or gate.get('skill_gate_blocked') is not False
            or gate.get('skill_gate_isolation_verified') is not True
            or type(gate.get('skill_gate_isolation_violations')) is not int
            or gate['skill_gate_isolation_violations'] != 0
            or gate.get('skill_gate_context_continuity_verified') is not True
            or type(gate.get('skill_gate_session_count')) is not int
            or gate['skill_gate_session_count'] != 1 or not isinstance(session, str) or not session
            or gate.get('skill_gate_required_skills') != required):
        return result

    logs = run / 'logs/aut'
    def phase_data(path, initial=False):
        try:
            events = [json.loads(line) for line in (path / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            phase_result = json.loads((path / 'result.json').read_text(encoding='utf-8'))
            invocation = json.loads((path / 'invocation.json').read_text(encoding='utf-8'))
            ids = [event.get('thread_id') for event in events if event.get('type') == 'thread.started']
            valid = (type(phase_result.get('returncode')) is int and phase_result['returncode'] == 0
                     and phase_result.get('timed_out') is False
                     and phase_result.get('stdin_delivery_verified') is True
                     and phase_result.get('session_id') == session and ids == [session]
                     and invocation.get('session_expected') == (None if initial else session)
                     and any(e.get('type') == 'turn.completed' for e in events)
                     and not any(e.get('type') in ('turn.failed', 'error') for e in events))
            return events, phase_result, invocation, valid
        except (OSError, ValueError, TypeError, AttributeError):
            return [], {}, {}, False

    # The transition and resumed B must be evidenced independently of the
    # certification label; B events establish continuity, never a prior read.
    _, _, _, phase_b_valid = phase_data(logs / 'phase_b')
    if not phase_b_valid:
        return result
    initial_reads, retry_reads = set(), set()
    retries = gate.get('skill_gate_retry_count')
    attempts = gate.get('skill_gate_read_attempts')
    if (type(retries) is not int or not 0 <= retries <= 10 or type(attempts) is not int
            or attempts != retries + 1):
        return result
    retry_dirs = sorted(p for p in (logs / 'retries').glob('attempt_*') if p.is_dir())
    if [path.name for path in retry_dirs] != [f'attempt_{index:02d}' for index in range(1, retries + 1)]:
        return result
    directories = [logs / 'phase_a'] + retry_dirs
    for index, path in enumerate(directories):
        events, phase_result, _, valid = phase_data(path, initial=index == 0)
        if not valid:
            return result
        verdict = evaluate_read_evidence(run, metadata, events, returncode=phase_result['returncode'],
                                         timed_out=phase_result['timed_out'], evidence_dir=path.relative_to(logs))
        if verdict['status'] not in ('evidence_verified', 'verification_failed'):
            return result
        (initial_reads if index == 0 else retry_reads).update(verdict['verified_skills'])

    # A failed check by itself is not proof of non-delivery. A negative
    # conclusion requires a demonstrated transition, complete protected turn
    # logs, a missing verified read, and an explicitly absent fallback.
    if gate.get('skill_gate_context_delivery_verified') is False:
        if (gate.get('skill_gate_fallback_used') is False
                and not (logs / 'fallback').exists()
                and any(skill not in initial_reads | retry_reads for skill in required)):
            result['skill_delivery_before_write'] = False
        return result
    if (gate.get('skill_gate_certification') not in ('CERTIFIED', 'PARTIALLY_VERIFIED')
            or gate.get('skill_gate_context_delivery_verified') is not True
            or gate.get('skill_gate_verified_skills') != required
            or set(methods) != set(required)):
        return result

    fallback_skills = [skill for skill in required if methods.get(skill) == 'preloaded_fallback']
    fallback_valid = (not fallback_skills and gate.get('skill_gate_fallback_used') is False
                      and gate.get('skill_gate_fallback_skills') == [] and not (logs / 'fallback').exists())
    if fallback_skills and (gate.get('skill_gate_fallback_used') is True
            and gate.get('skill_gate_fallback_sha256_verified') is True
            and gate.get('skill_gate_fallback_skills') == fallback_skills):
        _, _, invocation, valid = phase_data(logs / 'fallback')
        try:
            payload = (logs / 'fallback/prompt_sent.md').read_bytes()
            valid = (valid and invocation.get('stdin_bytes') == len(payload)
                     and invocation.get('stdin_sha256') == hashlib.sha256(payload).hexdigest())
            for skill in fallback_skills:
                start = b'\nBEGIN SKILL ' + skill.encode() + b'\n'
                end = b'\nEND SKILL ' + skill.encode() + b'\n'
                if payload.count(start) != 1 or payload.count(end) != 1:
                    valid = False
                    break
                content = payload.split(start, 1)[1].split(end, 1)[0]
                key = 'dns_skill_sha256' if skill == 'kathara-dns' else 'creation_skill_sha256'
                valid = valid and bool(metadata.get(key)) and hashlib.sha256(content).hexdigest() == metadata[key]
            fallback_valid = bool(valid)
        except (OSError, ValueError, TypeError):
            fallback_valid = False
    if not fallback_valid:
        return result

    for skill in required:
        method = methods.get(skill)
        if method == 'read_verified' and skill in initial_reads:
            autonomous = True
        elif method == 'retry_verified' and skill in retry_reads and skill not in initial_reads:
            autonomous = True
        elif method == 'preloaded_fallback' and skill not in initial_reads | retry_reads:
            autonomous = False
        else:
            continue
        details[skill].update(autonomous_read_before_write=autonomous, delivery_before_write=True)
    if all(value['delivery_before_write'] is True for value in details.values()):
        result['skill_delivery_before_write'] = True
        result['skill_autonomous_read_before_write'] = all(value['autonomous_read_before_write'] is True for value in details.values())
        # These legacy fields are updated only for recovery_v1. Protocol
        # compliance means verified delivery; strict_status distinguishes fallback.
        compliance['required_reads_complete_before_modification'] = result['skill_autonomous_read_before_write']
        compliance['protocol_compliance_observed'] = True
        compliance['strict_status'] = 'verified' if result['skill_autonomous_read_before_write'] else 'fallback_delivered'
        compliance['status'] = compliance['strict_status']
        for skill, value in details.items():
            observed = compliance['skill_details'][skill]
            observed['read_before_modification'] = value['autonomous_read_before_write']
            observed['verification_status'] = 'verified' if value['autonomous_read_before_write'] else 'fallback_delivered'
    return result


def make_metrics(run: Path, metadata: dict, *, total_seconds: float | None,
                 checker_seconds: float | None, checker_outcome: dict | None) -> dict:
    logs = run / "logs/aut"
    events = load_jsonl(logs / "events.jsonl")
    agent = metadata.get("agent")
    available = metadata.get("available_skills") if isinstance(metadata.get("available_skills"), list) else None
    if agent == "antigravity":
        tokens = antigravity_usage(events)
    else:
        tokens = codex_usage(events)
    agent_seconds = _duration(logs / "result.json", "duration_seconds")
    sandbox_overhead = _duration(logs / "result.json", "sandbox_overhead_seconds")
    sandbox_meta = _sandbox_meta(logs)
    status = metadata.get("pipeline_state", metadata.get("status"))
    agent_success = metadata.get("aut_execution_success")
    correction_sha = metadata.get("correction_sha256")
    forced = metadata.get("forced_skills") if isinstance(metadata.get("forced_skills"), list) else None
    
    from .aut_observation import observe
    internet, skill_compliance = observe(run, metadata, events)
    protocol = metadata.get("skill_protocol")
    from .skill_gate import read_gate_metrics
    gate = read_gate_metrics(run)
    delivery = {'skill_autonomous_read_before_write': None,
                'skill_delivery_before_write': None, 'skill_delivery_details': None}
    if gate.get('skill_gate_recovery_policy_version') == 'recovery_v1':
        # The compatibility stream contains several turns; its last usage is
        # only phase B. The runner result holds their non-overlapping sum.
        try:
            result_usage = json.loads((logs / 'result.json').read_text()).get('usage')
        except (OSError, ValueError):
            result_usage = None
        tokens = codex_usage([{'type': 'turn.completed', 'usage': result_usage}])
    if (gate.get('skill_gate_recovery_policy_version') == 'recovery_v1'
            and protocol == 'enforced_read_v1' and agent == 'codex'
            and metadata.get('skill_mode') in ('dns_only', 'creation_only', 'both_forced')):
        protected = []
        paths = [logs / 'phase_a/events.jsonl'] + sorted((logs / 'retries').glob('attempt_*/events.jsonl'))
        for path in paths:
            for event in load_jsonl(path):
                item = event.get('item')
                if (isinstance(item, dict) and item.get('type') == 'command_execution'
                        and event.get('type') == 'item.completed'
                        and (type(item.get('exit_code')) is not int or item['exit_code'] != 0)):
                    continue
                event = dict(event)
                if isinstance(item, dict) and item.get('id'):
                    event['item'] = {**item, 'id': str(path.parent.relative_to(logs)) + ':' + item['id']}
                protected.append(event)
        # Network observations include all phases; autonomous reading metrics
        # exclude both fallback input and all reads after unlocking.
        _, skill_compliance = observe(run, metadata, protected, trace_path=logs / 'phase_a/events.jsonl')
        delivery = _recovery_delivery_metrics(run, metadata, gate, skill_compliance)
        if delivery['skill_delivery_before_write'] is not True and skill_compliance.get('required_skills'):
            skill_compliance['status'] = skill_compliance['strict_status'] = (
                'delivery_failed' if delivery['skill_delivery_before_write'] is False else 'unverified')
            skill_compliance['protocol_compliance_observed'] = False if delivery['skill_delivery_before_write'] is False else None
            skill_compliance['required_reads_complete_before_modification'] = None
            skill_compliance['required_complete_read_count'] = None
            skill_compliance['required_unverified_read_count'] = None
            for skill in skill_compliance['required_skills']:
                entry = skill_compliance['skill_details'][skill]
                detail = (delivery.get('skill_delivery_details') or {}).get(skill) or {}
                autonomous = detail.get('autonomous_read_before_write')
                if detail.get('delivery_before_write') is True and type(autonomous) is bool:
                    entry.update(complete_read_verified=True if autonomous else None,
                                 dedicated_read=True if autonomous else None,
                                 read_before_modification=autonomous,
                                 verification_status='verified' if autonomous else 'fallback_delivered')
                else:
                    entry.update(complete_read_verified=None, dedicated_read=None,
                                 read_before_modification=None, verification_status='unverified')
        skill_compliance.update(delivery)
    return {
        **gate,
        **delivery,
        "internet": internet,
        "skill_compliance": skill_compliance,
        "scenario": metadata.get("scenario_id", metadata.get("scenario")),
        "scenario_id": metadata.get("scenario_id", metadata.get("scenario")),
        "prompt_type": metadata.get("prompt_type"),
        "prompt_sha256": metadata.get("prompt_sha256"),
        "prompt_sent_sha256": metadata.get("prompt_sent_sha256"),
        "skill_mode": metadata.get("skill_mode"),
        "skill_protocol": protocol,
        "run_number": metadata.get("run_number", metadata.get("repetition")),
        "replicate": metadata.get("replicate"),
        "experiment_id": metadata.get("experiment_id"),
        "run_id": metadata.get("run_id"),
        "agent": agent,
        "model": metadata.get("model"),
        "reasoning_effort": metadata.get("reasoning_effort"),
        "available_skills": available,
        "forced_skills": forced,
        "agent_success": agent_success,
        "status": status,
        "execution_backend": metadata.get("execution_backend"),
        "authentication": metadata.get("authentication") or (
            "sbx_oauth_proxy" if metadata.get("execution_backend") == "docker_sandbox" else None
        ),
        "codex_host_version": metadata.get("codex_host_version") or sandbox_meta.get("codex_host_version"),
        "codex_sandbox_version": metadata.get("codex_sandbox_version") or sandbox_meta.get("codex_sandbox_version"),
        "sandbox": {
            "name": sandbox_meta.get("sandbox_name") or metadata.get("sandbox_name"),
            "id": sandbox_meta.get("sandbox_id") or metadata.get("sandbox_id"),
            "sbx_version": sandbox_meta.get("sbx_version") or metadata.get("sbx_version"),
            "codex_host_version": sandbox_meta.get("codex_host_version") or metadata.get("codex_host_version"),
            "codex_sandbox_version": sandbox_meta.get("codex_sandbox_version") or metadata.get("codex_sandbox_version"),
            "cleanup_ok": sandbox_meta.get("cleanup_ok") if sandbox_meta.get("cleanup_ok") is not None else metadata.get("sandbox_cleanup_ok"),
            "cleanup_error": sandbox_meta.get("cleanup_error") or metadata.get("sandbox_cleanup_error"),
            "error": sandbox_meta.get("error") or metadata.get("sandbox_error"),
        } if (sandbox_meta or metadata.get("execution_backend") == "docker_sandbox") else None,
        "pipeline_error": metadata.get("pipeline_error"),
        "timing": {
            "agent_seconds": agent_seconds,
            "sandbox_overhead_seconds": sandbox_overhead,
            "checker_seconds": checker_seconds,
            "total_seconds": total_seconds,
        },
        "tokens": tokens,
        "llm_sampling": _sampling_meta(run),
        "checker": _checker_summary(run, checker_outcome),
        "correction_sha256": correction_sha,
        "evaluation_revision": metadata.get("evaluation_revision", 0),
        "last_reevaluated_at": metadata.get("last_reevaluated_at"),
    }



def print_run_summary(metrics: dict) -> None:
    from .terminal_ui import result
    result(metrics)
