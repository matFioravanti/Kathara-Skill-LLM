"""Comparable experimental conditions; legacy fields remain explicitly unverified."""
import hashlib
import json
import importlib.metadata
import sys

from .config import skill_paths
from .correction_input import correction_path
from .prompts import resolve_prompt, render_task_prompt
from .skill_modes import mode_details, execution_prompt
from .workspace import tree_hash


def conditions(config, scenario, prompt_type, mode, assignment=None, *, agent=None):
    agent = agent or config.data['aut']['agent']
    prompt = resolve_prompt(config.root, assignment.dns_tree_id if assignment else scenario.scenario_id,
                            prompt_type, assignment.task_level if assignment else None)
    rendered = render_task_prompt(config.root, assignment, prompt_type)[1] if assignment else prompt.read_text(encoding='utf-8')
    correction = correction_path(config.root, assignment) if assignment else scenario.correction
    paths = skill_paths(config, mode_details(mode).available_skills) if agent == 'codex' else {}
    if agent != 'codex' and config.data['aut'].get('dns_skill'):
        paths = {'kathara-dns': config.path(config.data['aut']['dns_skill'])}
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    versions = {}
    for package in ('kathara', 'kathara-lab-checker', 'inspect-ai', 'inspect-swe', 'PyYAML'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        'version': 1, 'agent': agent, 'model': config.model(),
        'reasoning_effort': config.reasoning_effort(),
        'aut': config.data.get('aut', {}),
        'sandbox': config.data.get('sandbox', {}),
        'docker_sandbox': config.data.get('docker_sandbox', {}),
        'checker': config.data.get('checker', {}),
        'python_version': sys.version, 'component_versions': versions,
        'timeout_seconds': config.data.get('benchmark', {}).get('timeout_seconds'),
        'skill_mode': mode, 'prompt_sha256': digest(prompt),
        'rendered_prompt_sha256': hashlib.sha256(rendered.encode('utf-8')).hexdigest(),
        'effective_prompt_sha256': hashlib.sha256(execution_prompt(mode, rendered).encode('utf-8')).hexdigest(),
        'correction_sha256': digest(correction), 'source_lab_sha256': tree_hash(scenario.lab),
        'skills': {name: {'sha256': digest(path), 'bundle_sha256': tree_hash(path.parent)}
                   for name, path in sorted(paths.items())},
    }


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def missing_conditions(value):
    missing = [key for key in ('agent', 'model', 'reasoning_effort', 'python_version') if not value.get(key)]
    if not isinstance(value.get('aut'), dict) or not value['aut'].get('version'):
        missing.append('aut.version')
    versions = value.get('component_versions')
    if not isinstance(versions, dict) or not versions or any(v is None for v in versions.values()):
        missing.append('component_versions')
    return missing


def compare(manifest, expected):
    """Return compatible, conflict, or unverified and auditable field names."""
    recorded = manifest.get('experimental_conditions')
    if isinstance(recorded, dict):
        differences = [key for key in sorted(set(recorded) | set(expected)) if recorded.get(key) != expected.get(key)]
        actual_hash = manifest.get('experimental_fingerprint')
        if actual_hash != fingerprint(recorded):
            return 'conflict', ['experimental_fingerprint non valida']
        for key in ('agent', 'model', 'reasoning_effort', 'skill_mode', 'prompt_sha256', 'correction_sha256', 'source_lab_sha256'):
            if key in manifest and manifest.get(key) != recorded.get(key):
                differences.append(f'{key} incoerente nel manifest')
        if differences:
            return 'conflict', differences
        missing = missing_conditions(recorded)
        return ('unverified', missing) if missing else ('compatible', [])
    legacy_map = {'agent': 'agent', 'model': 'model', 'reasoning_effort': 'reasoning_effort',
                  'prompt_sha256': 'prompt_sha256', 'correction_sha256': 'correction_sha256',
                  'source_lab_sha256': 'source_lab_sha256', 'skill_mode': 'skill_mode'}
    differences = [old for old, new in legacy_map.items()
                   if manifest.get(old) is not None and manifest.get(old) != expected.get(new)]
    for old, value in [('agent_version', expected['aut'].get('version')),
                       ('skill_protocol', expected['aut'].get('skill_protocol', 'explicit_read_v2')),
                       ('timeout_seconds', expected['timeout_seconds'])]:
        if manifest.get(old) is not None and manifest.get(old) != value:
            differences.append(old)
    for name, key in [('kathara-dns', 'dns_skill_sha256'), ('kathara-creation', 'creation_skill_sha256')]:
        if name in expected['skills'] and manifest.get(key) is not None and manifest[key] != expected['skills'][name]['sha256']:
            differences.append(key)
    return ('conflict', differences) if differences else ('unverified', ['fingerprint storica assente'])
