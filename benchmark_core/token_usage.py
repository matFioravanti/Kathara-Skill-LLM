"""Derived token accounting. Raw provider events/results are never rewritten."""
from pathlib import Path
import hashlib
import json
import re

FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens',
          'reasoning_output_tokens', 'cache_write_input_tokens', 'total_tokens')
SCHEMA = 'codex_token_accounting_v1'


def runtime_version(version):
    match = re.fullmatch(r'(?:codex-cli\s+|v)?(\d+\.\d+\.\d+)', str(version or '').strip())
    return match[1] if match else None


def semantics_for(agent, backend, version):
    # Empirically verified against total_token_usage in Codex session state.
    # Do not extend this table based on version ordering or the model name.
    if agent == 'codex' and backend == 'docker_sandbox' and runtime_version(version) == '0.165.0':
        return 'cumulative_thread'
    return 'unknown'


def number(value):
    return value if type(value) is int and value >= 0 else None


def read(path):
    try:
        item = json.loads(Path(path).read_text())
        return item if isinstance(item, dict) else {}
    except (OSError, ValueError):
        return {}


def events_at(directory):
    result = []
    try:
        for line in (Path(directory)/'events.jsonl').read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError('non-object event')
                result.append(item)
    except (OSError, ValueError):
        return [], False
    return result, True


def save(path, value):
    path = Path(path)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)+'\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != raw:
        path.write_bytes(raw)


def evidence(directory):
    directory = Path(directory).resolve()
    return {'directory': str(directory), 'sha256': {
        name: hashlib.sha256((directory/name).read_bytes()).hexdigest()
        for name in ('events.jsonl', 'result.json', 'invocation.json') if (directory/name).is_file()}}


class UsageLedger:
    """Independent per-thread, per-field state; gaps never become zeroes."""

    def __init__(self):
        self.threads = {}

    def invalidate(self, thread_id=None):
        for key,state in self.threads.items():
            if thread_id is None or key == thread_id:
                state['previous'] = dict.fromkeys(FIELDS)
                state['history_complete'] = False

    def consume(self, raw, *, thread_id=None, new_thread=None, expected_thread=None,
                semantics='unknown', identity_verified=True):
        raw = raw if isinstance(raw, dict) else None
        diagnostics, delta = {}, dict.fromkeys(FIELDS)
        identity_error = None
        if semantics == 'cumulative_thread':
            if not identity_verified or not isinstance(thread_id, str) or not thread_id:
                identity_error = 'thread_identity_unverified'
            elif expected_thread is not None and expected_thread != thread_id:
                identity_error = 'thread_continuity_lost'
            elif thread_id in self.threads and new_thread is True:
                identity_error = 'existing_thread_claimed_as_new'
        state = self.threads.get(thread_id)
        if identity_error:
            self.invalidate(expected_thread or thread_id)
        elif semantics == 'unknown':
            self.invalidate(thread_id or expected_thread)
        if semantics == 'cumulative_thread' and not identity_error and state is None:
            state = {'previous':dict.fromkeys(FIELDS, 0 if new_thread is True else None),
                     'poisoned':set(), 'history_complete':new_thread is True}
            self.threads[thread_id] = state
        for key in FIELDS:
            current = number(raw.get(key)) if raw is not None else None
            if identity_error or semantics not in ('per_turn', 'cumulative_thread'):
                diagnostics[key] = identity_error or 'usage_semantics_unverified'
            elif current is None:
                diagnostics[key] = 'counter_missing' if raw is None or key not in raw else 'counter_invalid_or_null'
                if state is not None:
                    state['previous'][key] = None
            elif semantics == 'per_turn':
                delta[key] = current
            elif key in state['poisoned']:
                diagnostics[key] = 'counter_history_incoherent'
            else:
                previous = state['previous'][key]
                if previous is None:
                    diagnostics[key] = 'previous_counter_unknown'
                elif current < previous:
                    diagnostics[key] = 'counter_regressed'
                    state['poisoned'].add(key)
                else:
                    delta[key] = current-previous
                state['previous'][key] = current
        available = [key for key in FIELDS if raw is not None and key in raw]
        verified = (all(delta[key] is not None for key in ('input_tokens', 'output_tokens'))
                    and all(delta[key] is not None for key in available))
        return {'schema':SCHEMA, 'kind':'turn', 'thread_id':thread_id,
                'usage_raw':raw, 'usage_delta':delta, 'usage_semantics':semantics,
                'usage_verified':verified, 'usage_diagnostics':diagnostics,
                'history_complete':state['history_complete'] if state else semantics == 'per_turn'}


def record_turn(directory, ledger, *, version=None, backend='docker_sandbox', history=(), order_verified=True):
    directory = Path(directory)
    result, invocation = read(directory/'result.json'), read(directory/'invocation.json')
    events, valid_trace = events_at(directory)
    ids = [item.get('thread_id') for item in events if item.get('type') == 'thread.started']
    identity = len(ids) == 1 and isinstance(ids[0], str) and bool(ids[0])
    thread = ids[0] if identity else None
    if result.get('session_id') is not None and result['session_id'] != thread:
        identity = False
    if 'session_expected' in invocation:
        expected = invocation['session_expected']
        new = expected is None
        identity = identity and (expected is None or isinstance(expected, str) and bool(expected))
    else:
        command = invocation.get('command') or []
        starts = [i for i,v in enumerate(command) if isinstance(v,str) and Path(v).name == 'codex']
        args = command[starts[-1]+1:] if starts else []
        new = bool(args and args[0] == 'exec' and 'resume' not in args)
        expected = None
        if 'resume' in args:
            at = args.index('resume')
            expected = args[at+1] if len(args)>at+1 else None
            new = False
    usage_events = [e['usage'] for e in events if e.get('type') in ('turn.completed','turn.failed')
                    and isinstance(e.get('usage'),dict)]
    raw = usage_events[-1] if usage_events else result.get('usage')
    if usage_events and result.get('usage') is not None and result['usage'] != raw:
        identity = False
    version = invocation.get('codex_sandbox_version') or version
    item = ledger.consume(raw, thread_id=thread, new_thread=new,
                          expected_thread=expected, identity_verified=identity and valid_trace and order_verified,
                          semantics=semantics_for('codex',backend,version))
    item.update(codex_version=version, execution_backend=backend,
                outcome='completed' if result.get('returncode') == 0 and not result.get('timed_out') else 'failed_or_partial',
                sources=[*history,evidence(directory)])
    if not order_verified:
        item['usage_diagnostics']['order'] = 'chronological_order_unverified'
    return item


def normalize_session(session):
    """Replays the ordered live turn list, including gate and failed attempts.

    Earlier sidecars are byte-identical: checkpoints/receipts remain valid.
    Unrecognised runtimes keep legacy values explicitly unverified.
    """
    if runtime_version(session.version) is None:
        return []
    ledger, history, items = UsageLedger(), [], []
    for directory, _ in session.turns:
        item = record_turn(directory,ledger,version=session.version,history=history)
        save(Path(directory)/'usage_accounting.json',item)
        history = item['sources']
        items.append(item)
    return items


def normalize_standalone(directory, version):
    if runtime_version(version) is not None:
        save(Path(directory)/'usage_accounting.json',record_turn(directory,UsageLedger(),version=version))


def load_accounting(directory):
    directory = Path(directory)
    path = directory/'usage_accounting.json'
    if not path.exists():
        return None
    item = read(path)
    valid = item.get('schema') == SCHEMA and isinstance(item.get('usage_delta'),dict)
    sources = item.get('sources')
    valid = valid and isinstance(sources,list) and bool(sources)
    if valid:
        for source in sources:
            try:
                valid = valid and evidence(source['directory']) == source
            except (KeyError, OSError, TypeError):
                valid = False
    if item.get('kind') == 'turn':
        # A stage may contain the same evidence copied from logs/aut/turn.
        # Additional timing fields in its result do not alter provider usage.
        result = read(directory/'result.json')
        events, parsed = events_at(directory)
        valid = valid and parsed
        raw = [e.get('usage') for e in events if e.get('type') in ('turn.completed','turn.failed')
               and isinstance(e.get('usage'),dict)]
        valid = valid and (not raw or raw[-1] == item.get('usage_raw'))
        valid = valid and (result.get('usage') == item.get('usage_raw')
                           or result.get('usage') is None and bool(raw))
    if not valid:
        return {'schema':SCHEMA, 'usage_semantics':'unverifiable', 'usage_verified':False,
                'usage_delta':dict.fromkeys(FIELDS), 'usage_diagnostics':{'evidence':'accounting_evidence_changed'}}
    return item


def effective_usage(directory, result=None):
    accounting = load_accounting(directory)
    if accounting is not None:
        return accounting['usage_delta']
    return (result or read(Path(directory)/'result.json')).get('usage')


def sum_counters(usages):
    return {key:sum(values) if values and all(number(v) is not None for v in values) else None
            for key in FIELDS for values in [[u.get(key) if isinstance(u,dict) else None for u in usages]]}


def aggregate_accounting(items, *, raw=None):
    diagnostics = {str(i):item.get('usage_diagnostics') for i,item in enumerate(items)
                   if not item.get('usage_verified')}
    return {'schema':SCHEMA, 'kind':'aggregate', 'usage_raw':raw,
            'usage_delta':sum_counters([item['usage_delta'] for item in items]),
            'usage_semantics':'aggregate_delta',
            'usage_verified':bool(items) and all(item.get('usage_verified') for item in items),
            'usage_diagnostics':diagnostics, 'history_complete':bool(items) and all(item.get('history_complete') for item in items),
            'sources':list({s['directory']:s for item in items for s in item.get('sources',[])}.values())}


def save_session_aggregate(session, directory):
    items = normalize_session(session)
    if items:
        save(Path(directory)/'usage_accounting.json',aggregate_accounting(items,raw=read(Path(directory)/'result.json').get('usage')))
