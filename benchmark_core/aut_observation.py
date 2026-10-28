"""Osservazioni conservative dai soli eventi AUT, mai dal prompt o dal checker."""
import ipaddress
import json
import re
from urllib.parse import urlsplit

from .skill_modes import SKILL_MODES

SKILLS = ("kathara-creation", "kathara-dns")
NETWORK = re.compile(r"\b(?:curl|wget|httpie|ssh|scp|sftp|nc|netcat|telnet|ping|traceroute|dig|nslookup|host)\b", re.I)
READ = re.compile(r"\b(?:cat|sed|head|tail|less|more|awk|bat|read_file|readfile|open|python\w*|perl)\b", re.I)
URL = re.compile(r"https?://[^\s\"'<>\\]+", re.I)


def _domains(value):
    domains = set()
    for url in URL.findall(value):
        try:
            host = urlsplit(url).hostname
            if not host or host == 'localhost' or '.' not in host or host.endswith(('.local', '.internal', '.test')):
                continue
            try:
                if not ipaddress.ip_address(host).is_global:
                    continue
            except ValueError:
                pass
            domains.add(host.lower())
        except ValueError:
            pass
    return domains


def observe(run, metadata, events):
    path = run / 'logs/aut/events.jsonl'
    trace = path.is_file() and bool(events)
    # Merge lifecycle updates by item ID. No IDs: each event stands alone.
    items = {}
    for index, event in enumerate(events):
        item = event.get('item')
        if isinstance(item, dict):
            key = ('item', item.get('id', index))
            old = items.setdefault(key, {})
            old.update({k: v for k, v in item.items() if v is not None})
            old['_event_type'] = event.get('type')
        elif event.get('event') in ('tool_call', 'tool_use', 'tool_result'):
            obj = event.get('tool') if isinstance(event.get('tool'), dict) else event
            key = ('tool', obj.get('id') or obj.get('tool_call_id') or index)
            old = items.setdefault(key, {})
            old.update({k: v for k, v in obj.items() if v is not None})
            old['_event_type'] = event.get('event')
    attempts = calls = candidates = 0
    domains = set()
    observed = set()
    other_external = False
    for item in items.values():
        kind = str(item.get('type') or item.get('name') or item.get('tool_name') or '').lower()
        name = str(item.get('name') or item.get('tool_name') or item.get('tool') or '').lower()
        server = str(item.get('server') or '').lower()
        status = str(item.get('status') or '').lower()
        completed = item.get('_event_type') in ('item.completed', 'tool_result') or status in ('completed', 'success', 'succeeded')
        failed = status in ('failed', 'error', 'cancelled') or item.get('error') is not None or item.get('is_error') is True
        successful = completed and not failed
        if kind == 'web_search' or name in ('web_search', 'search_web', 'google_search'):
            attempts += 1
            if successful:
                calls += 1
                domains.update(_domains(json.dumps(item.get('result', ''), ensure_ascii=False)))
        if kind == 'mcp_tool_call' and (re.search(r'web.*search|search.*web', name) or (server == 'web' and 'search_query' in str(item.get('arguments') or ''))):
            attempts += 1
            if successful:
                calls += 1
                domains.update(_domains(json.dumps(item.get('result', ''), ensure_ascii=False)))
        elif kind == 'mcp_tool_call' and (server in ('web', 'browser') or re.search(r'(^|[._])(?:web|browser)[._]', name)) and successful:
            other_external = True
            domains.update(_domains(json.dumps(item.get('result', ''), ensure_ascii=False)))
        command = item.get('command') or (item.get('input') if isinstance(item.get('input'), str) else '')
        if kind in ('command_execution', 'shell', 'run_command', 'terminal') or name in ('run_command', 'shell', 'terminal'):
            if isinstance(command, str) and NETWORK.search(command):
                candidates += 1
        input_data = item.get('input') or item.get('arguments') or ''
        inp = json.dumps(input_data, ensure_ascii=False) if isinstance(input_data, dict) else str(input_data)
        output = item.get('aggregated_output') or item.get('output') or item.get('result') or ''
        out = json.dumps(output, ensure_ascii=False) if not isinstance(output, str) else output
        for skill in SKILLS:
            skill_path = skill + '/SKILL.md'
            is_dns_temp = skill == 'kathara-dns' and 'antigravity_skills/SKILL.md' in (str(command) + inp)
            explicit = skill_path in (str(command) + inp) or is_dns_temp
            reader = READ.search(str(command)) or name in ('read_file', 'view_file')
            # Content identifies the file even when a later command in a chain failed.
            content = bool(re.search(r'(?m)^name:\s*["\']?' + re.escape(skill) + r'\s*["\']?\s*$', out))
            if explicit and reader and completed and content:
                observed.add(skill)
            if kind in ('skill', 'skill_invocation') and (item.get('name') == skill) and successful:
                observed.add(skill)
    policy = None
    try:
        sandbox = json.loads((run / 'logs/aut/sandbox_metadata.json').read_text())
        policy = sandbox.get('network_policy')
    except (OSError, ValueError, AttributeError):
        pass
    confirmed = calls > 0 or other_external
    internet = {'internet_used': True if confirmed else None,
                'status': 'external_web_search_observed' if calls else 'external_resource_observed' if other_external else 'network_attempt_unconfirmed' if candidates or attempts else 'unknown',
                'web_search_calls': calls if trace else None, 'web_search_attempts': attempts if trace else None,
                'external_domains': sorted(domains), 'shell_network_candidates': candidates if trace else None,
                'network_policy': policy, 'trace_available': trace, 'detection_source': 'aut_events' if trace else None}
    agent, mode = metadata.get('agent'), metadata.get('skill_mode')
    if agent == 'antigravity':
        required = ['kathara-dns']
    elif agent == 'codex' and mode in SKILL_MODES:
        required = list(SKILL_MODES[mode].forced_skills)
    else:
        required = None
    states = {skill: ('observed' if skill in observed else 'unknown') if required is None or skill in required else 'not_required' for skill in SKILLS}
    all_observed = (all(s in observed for s in required) if required else None)
    if required and not all_observed:
        all_observed = None
    compliance = {'skill_mode': mode, 'required_skills': required, 'observed_read_skills': sorted(observed),
                  'skill_states': states, 'required_reads_observed': all_observed,
                  'status': 'unknown' if required is None or (required and all_observed is None) else 'verified' if required else 'not_required'}
    return internet, compliance
