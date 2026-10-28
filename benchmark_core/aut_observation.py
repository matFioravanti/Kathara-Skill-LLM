"""Osservazioni conservative dai soli eventi AUT, mai dal prompt o dal checker."""
import ipaddress
import json
import re
import shlex
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .skill_modes import SKILL_MODES

SKILLS = ('kathara-creation', 'kathara-dns')
NETWORK = {'curl', 'wget', 'http', 'httpie', 'ssh', 'scp', 'sftp', 'nc', 'netcat', 'telnet', 'ping', 'ping6', 'traceroute', 'traceroute6'}
DNS = {'dig', 'host', 'nslookup'}
READ = {'cat', 'sed', 'head', 'tail', 'less', 'more', 'awk', 'bat'}
URL = re.compile(r'https?://[^\s"\'<>\\]+', re.I)


def _domains(value):
    """URL in output testuale o nei campi URL; non interpreta snippet come visite."""
    if isinstance(value, dict):
        return set().union(*(_domains(v) for k, v in value.items()
                             if k in ('url', 'uri', 'href', 'link', 'results', 'result', 'content', 'output', 'outputs')), set())
    if isinstance(value, list):
        return set().union(*(_domains(v) for v in value), set())
    if not isinstance(value, str):
        return set()
    domains = set()
    for url in URL.findall(value):
        try:
            host = urlsplit(url.rstrip('.,;:!?)]}')).hostname
            if not host:
                continue
            host = host.rstrip('.').lower()
            if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.test')):
                continue
            try:
                if not ipaddress.ip_address(host).is_global:
                    continue
            except ValueError:
                if '.' not in host:
                    continue
                host = host.encode('idna').decode('ascii')
            domains.add(host)
        except (ValueError, UnicodeError):
            continue
    return domains


def _destination(value):
    """Classifica soltanto destinazioni chiaramente presenti, senza DNS lookup."""
    value = value.lstrip('@')
    try:
        if '://' in value:
            value = urlsplit(value).hostname or ''
        elif '@' in value:
            value = value.rsplit('@', 1)[1].split(':', 1)[0]
        value = value.strip('[]').rstrip('.').lower()
        if value == 'localhost' or value.endswith(('.localhost', '.local', '.internal', '.test')):
            return 'local'
        try:
            return 'external' if ipaddress.ip_address(value).is_global else 'local'
        except ValueError:
            if re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', value) and not value.endswith(('.conf', '.md', '.txt', '.yaml', '.json')):
                return 'external'
    except ValueError:
        pass
    return 'unknown'


def _shell_commands(command, depth=0):
    """Tokenizer conservativo: riconosce eseguibili, non espande shell o sostituzioni."""
    if depth > 3 or not isinstance(command, str):
        return [], True
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars='|&;()<>\n')
        lexer.whitespace = ' \t\r'
        lexer.whitespace_split = True
        lexer.commenters = '#'
        tokens = list(lexer)
    except ValueError:
        return [], True
    commands, segment, uncertain = [], [], False
    def add_segment():
        nonlocal uncertain
        if not segment:
            return
        words = list(segment)
        while words and (re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', words[0]) or words[0] in ('sudo', 'env', 'command', 'exec', 'time', 'nohup')):
            words.pop(0)
        if not words:
            return
        exe = PurePosixPath(words[0]).name.lower()
        if exe in ('sh', 'bash', 'zsh', 'dash', 'ksh'):
            for i, arg in enumerate(words[1:], 1):
                if arg.startswith('-') and 'c' in arg[1:] and i + 1 < len(words):
                    nested, unsure = _shell_commands(words[i + 1], depth + 1)
                    commands.extend(nested)
                    uncertain |= unsure
                    return
            uncertain = True
        elif exe in NETWORK | DNS | READ:
            commands.append((exe, words[1:]))
        elif any('$(' in word or '`' in word for word in words):
            uncertain = True
    for token in tokens:
        if token in (';', '&&', '||', '|', '&', '(', ')', '\n'):
            add_segment()
            segment = []
        elif token and all(c in '<>' for c in token):
            # Redirections do not introduce executables; stop scanning this segment.
            segment.append(token)
        else:
            segment.append(token)
    add_segment()
    return commands, uncertain


def _network_command(command):
    commands, uncertain = _shell_commands(command)
    classes = set()
    for exe, args in commands:
        if exe not in NETWORK | DNS:
            continue
        # DNS queries name a lab zone, not necessarily an external resolver.
        targets = [a for a in args if a.startswith('@')] if exe == 'dig' else []
        if exe == 'nslookup' and len([a for a in args if not a.startswith('-')]) > 1:
            targets = [a for a in args if not a.startswith('-')][-1:]
        elif exe == 'host' and len([a for a in args if not a.startswith('-')]) > 1:
            targets = [a for a in args if not a.startswith('-')][-1:]
        elif exe not in DNS:
            targets = [a for a in args if not a.startswith('-')]
        destinations = {_destination(a) for a in targets}
        if 'external' in destinations:
            classes.add('external')
        elif 'local' in destinations:
            classes.add('local')
        else:
            classes.add('unknown')
    if uncertain:
        classes.add('unknown')
    return classes


def _items(events):
    items = {}
    for index, event in enumerate(events):
        item = event.get('item')
        namespace, phase = 'item', event.get('type')
        if not isinstance(item, dict) and event.get('event') == 'step_update':
            step = event.get('step_update')
            if not isinstance(step, dict) or step.get('step_type') != 'tool':
                continue
            item = dict(step)
            item['id'] = step.get('step_id')
            item['name'] = step.get('tool_name')
            item['input'] = step.get('inputs')
            item['output'] = step.get('outputs')
            item['status'] = step.get('state')
            namespace, phase = 'step', 'step_update'
        elif not isinstance(item, dict) and event.get('event') in ('tool_call', 'tool_use', 'tool_result'):
            item = event.get('tool') if isinstance(event.get('tool'), dict) else event
            namespace, phase = 'tool', event.get('event')
        if not isinstance(item, dict):
            continue
        key = (namespace, item.get('id') or item.get('tool_call_id') or index)
        old = items.setdefault(key, {})
        old.update({k: v for k, v in item.items() if v is not None})
        old['_event_type'] = phase
    return items.values()


def _visited_result_domains(value, require_view=False):
    if isinstance(value, list):
        return set().union(*(_visited_result_domains(v, require_view) for v in value), set())
    if isinstance(value, dict):
        if str(value.get('title', '')).lower() in ('internal error', 'error', 'not found'):
            return set()
        if require_view and not re.search(r'view\d+$', str(value.get('ref_id', ''))):
            return set()
        return _domains({k: value[k] for k in ('url', 'uri', 'href', 'link') if k in value})
    return set() if require_view else _domains(value)


def _output_text(value):
    if isinstance(value, dict):
        return '\n'.join(_output_text(v) for v in value.values())
    if isinstance(value, list):
        return '\n'.join(_output_text(v) for v in value)
    return str(value) if value is not None else ''


def observe(run, metadata, events):
    trace = (run / 'logs/aut/events.jsonl').is_file() and bool(events)
    attempts = calls = candidates = local = uncertain = 0
    result_domains, visited_domains, observed = set(), set(), set()
    other_external = False
    for item in _items(events):
        kind = str(item.get('type') or '').lower()
        name = str(item.get('name') or item.get('tool_name') or item.get('tool') or '').lower()
        server = str(item.get('server') or '').lower()
        status = str(item.get('status') or '').lower()
        completed = item.get('_event_type') in ('item.completed', 'tool_result') or status in ('completed', 'complete', 'success', 'succeeded', 'done', 'failed', 'error')
        failed = status in ('failed', 'error', 'cancelled') or item.get('error') is not None or item.get('is_error') is True
        successful = completed and not failed
        input_data = item.get('input') or item.get('arguments') or item.get('inputs') or {}
        inp = json.dumps(input_data, ensure_ascii=False) if isinstance(input_data, (dict, list)) else str(input_data)
        result = [item.get('result'), item.get('results')]
        action = item.get('action') if isinstance(item.get('action'), dict) else {}
        action_type = action.get('type')
        web = kind == 'web_search' or name in ('web_search', 'search_web', 'google_search')
        mcp_search = kind == 'mcp_tool_call' and (re.search(r'web.*search|search.*web', name) or (server == 'web' and 'search_query' in inp))
        is_search = (web and action_type in (None, 'search')) or mcp_search
        if is_search:
            attempts += 1
            if successful:
                calls += 1
                result_domains.update(_domains(result) | _domains(item.get('output') or ''))
        # A successful explicit open with an actual result URL is evidence of a visit;
        # an attempted open or an error result alone is not.
        open_tool = (web and action_type in ('open_page', 'other')) or (kind == 'mcp_tool_call' and (server in ('web', 'browser') or 'browser' in name) and re.search(r'open|visit|navigate', name)) or name in ('open_url', 'read_url_content', 'browse_url')
        if open_tool and successful:
            opened = _visited_result_domains(result, require_view=action_type == 'other') | _visited_result_domains(item.get('output') or '', require_view=action_type == 'other')
            if opened:
                other_external = True
                visited_domains.update(opened)
        command = item.get('command')
        if not command and isinstance(input_data, dict):
            command = input_data.get('command') or input_data.get('cmd') or input_data.get('CommandLine')
        elif not command and isinstance(input_data, str):
            command = input_data
        shell = kind in ('command_execution', 'shell', 'run_command', 'terminal') or name in ('run_command', 'shell', 'terminal', 'execute_command', 'command_execution')
        if shell and isinstance(command, str):
            classes = _network_command(command)
            candidates += 'external' in classes
            local += 'local' in classes
            uncertain += 'unknown' in classes
        output = item.get('aggregated_output') or item.get('output') or item.get('outputs') or item.get('result') or ''
        out = _output_text(output)
        commands, _ = _shell_commands(command) if isinstance(command, str) else ([], False)
        for skill in SKILLS:
            skill_path = skill + '/SKILL.md'
            explicit = skill_path in (str(command or '') + inp) or (skill == 'kathara-dns' and 'antigravity_skills/SKILL.md' in (str(command or '') + inp))
            reader = any(exe in READ and any(skill_path in arg or (skill == 'kathara-dns' and 'antigravity_skills/SKILL.md' in arg) for arg in args) for exe, args in commands) or name in ('read_file', 'view_file', 'readfile')
            content = bool(re.search(r'(?m)^name:\s*["\']?' + re.escape(skill) + r'\s*["\']?\s*$', out))
            if explicit and reader and completed and content:
                observed.add(skill)
            if kind in ('skill', 'skill_invocation') and item.get('name') == skill and successful:
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
                'external_domains': sorted(visited_domains) if trace else None, 'search_result_domains': sorted(result_domains) if trace else None, 'visited_domains': sorted(visited_domains) if trace else None,
                'shell_network_candidates': candidates if trace else None, 'shell_network_local': local if trace else None,
                'shell_network_uncertain': uncertain if trace else None,
                'network_policy': policy, 'trace_available': trace, 'detection_source': 'aut_events' if trace else None}
    agent, mode = metadata.get('agent'), metadata.get('skill_mode')
    if agent == 'antigravity':
        required = ['kathara-dns']
    elif agent == 'codex' and mode in SKILL_MODES:
        required = list(SKILL_MODES[mode].forced_skills)
    else:
        required = None
    states = {skill: ('observed' if skill in observed else 'unknown') if required is None or skill in required else 'not_required' for skill in SKILLS}
    all_observed = True if required and all(s in observed for s in required) else None
    compliance = {'skill_mode': mode, 'required_skills': required, 'observed_read_skills': sorted(observed),
                  'skill_states': states, 'required_reads_observed': all_observed,
                  'status': 'unknown' if required is None or (required and all_observed is None) else 'verified' if required else 'not_required'}
    return internet, compliance
