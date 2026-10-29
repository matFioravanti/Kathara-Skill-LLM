"""Fail-closed selection and evidence checks for the experimental Skill Gate.

No production backend is currently certified to run the protected read phase.
Do not replace this guard with a shell-only read-only flag: other AUT tools and
processes must be constrained as well.
"""
from pathlib import Path
import json

from .aut_observation import observe
from .skill_modes import mode_details
from .workspace import utc_now, write_json

PROTOCOL = 'enforced_read_v1'
FIELDS = ('skill_gate_enabled', 'skill_gate_status', 'skill_gate_required_skills',
          'skill_gate_verified_skills', 'skill_gate_read_seconds',
          'skill_gate_verification_seconds', 'skill_gate_blocked',
          'skill_gate_write_attempts_blocked', 'skill_gate_backend_enforcement',
          'skill_gate_input_tokens', 'skill_gate_output_tokens',
          'skill_gate_write_seconds', 'skill_gate_total_seconds',
          'write_phase_input_tokens', 'write_phase_output_tokens',
          'skill_gate_isolation_verified', 'skill_gate_isolation_violations',
          'skill_gate_context_strategy', 'skill_gate_backend',
          'skill_gate_protocol_version', 'skill_gate_state_history')


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
            'skill_gate_state_history': [{'status': 'unsupported_backend' if required else 'not_required', 'timestamp': utc_now()}]}


def enforce_or_block(config, run: Path, agent: str, mode: str):
    """Fail before AUT startup; there is currently no certified production backend."""
    if configured_protocol(config) != PROTOCOL:
        return
    if agent != 'codex':
        raise SkillGateError('unsupported_backend: enforced_read_v1 supports Codex only')
    required = mode_details(mode).forced_skills
    backend = ('docker_sandbox' if config.data.get('docker_sandbox', {}).get('execution_backend') == 'docker_sandbox' else 'codex_cli')
    record = gate_record(required, backend)
    logs = run / 'logs/aut'
    logs.mkdir(parents=True, exist_ok=True)
    write_json(logs / 'skill_gate.json', record)
    if required:
        raise SkillGateError(f'unsupported_backend: {backend} has no verified protected read phase')


def evaluate_read_evidence(run: Path, metadata: dict, events: list[dict], *, returncode: int | None, timed_out: bool):
    """Evaluate saved phase-A evidence; this function alone never opens the gate.

    A future backend must provide independently verified isolation, non-truncated
    trusted events, and lifecycle management before using this result.
    """
    required = list(mode_details(metadata['skill_mode']).forced_skills)
    if not required:
        return {'status': 'not_required', 'verified_skills': [], 'blocked': False}
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
    _, compliance = observe(run, metadata, safe_events)
    details = compliance['skill_details']
    verified = [s for s in required if details[s]['complete_read_verified'] is True and details[s]['dedicated_read'] is True]
    return {'status': 'evidence_verified' if len(verified) == len(required) else 'verification_failed',
            'verified_skills': verified, 'blocked': len(verified) != len(required)}


def read_gate_metrics(run: Path):
    try:
        data = json.loads((run / 'logs/aut/skill_gate.json').read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {field: data.get(field) for field in FIELDS}
    except (OSError, ValueError):
        pass
    return {field: None for field in FIELDS}
