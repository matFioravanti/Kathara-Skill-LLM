"""Opt-in, deterministic security probe; it does not run a model.

Run only with RUN_SBX_ISOLATION_TESTS=1 and a working local sbx daemon.
It demonstrates properties of a restricted process, not of the current AUT.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_SBX_ISOLATION_TESTS') != '1',
                                reason='requires explicit opt-in and local sbx daemon')


def call(*args):
    return subprocess.run(args, text=True, capture_output=True, timeout=180, check=False)


def test_read_only_bind_and_unprivileged_process():
    name = 'tesi-gate-test-' + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix='tesi-gate-', dir='/private/tmp') as directory:
        root = Path(directory)
        # Grant traversal for the sandbox's nobody user; protection is the ro mount.
        root.chmod(0o755)
        work, lab = root / 'work', root / 'lab'
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        lab.mkdir(mode=0o755)
        (lab / 'sub').mkdir(mode=0o755)
        (lab / 'lab.conf').write_text('baseline\n')
        (lab / 'lab.conf').chmod(0o644)
        (lab / 'r1.startup').write_text('startup\n')
        (lab / 'r1.startup').chmod(0o644)
        result = call('sbx', 'create', 'codex', str(work), str(lab) + ':ro',
                      '--name', name, '--skills', 'off', '--pull', 'missing')
        try:
            assert result.returncode == 0, result.stderr
            code = r'''
import json, os, pathlib, socket, subprocess, sys
lab = pathlib.Path(sys.argv[1]); work = pathlib.Path(sys.argv[2])
result = {}
result['readable'] = (lab / 'lab.conf').read_text() == 'baseline\n'
result['uid'] = os.getuid()
status = pathlib.Path('/proc/self/status').read_text()
result['no_new_privileges'] = 'NoNewPrivs:\t1' in status
result['zero_capabilities'] = 'CapEff:\t0000000000000000' in status
result['shell_write_denied'] = subprocess.run(['sh','-c','echo x > "$1/lab.conf"','sh',str(lab)], capture_output=True).returncode != 0
for name, operation in {
    'python_write_denied': lambda: (lab / 'lab.conf').write_text('x'),
    'create_denied': lambda: (lab / 'new').touch(),
    'remove_denied': lambda: (lab / 'sub').rmdir(),
    'chmod_denied': lambda: (lab / 'lab.conf').chmod(0o777),
    'chown_denied': lambda: os.chown(lab / 'lab.conf', os.getuid(), os.getgid()),
    'startup_write_denied': lambda: (lab / 'r1.startup').write_text('x'),
    'unlink_denied': lambda: (lab / 'r1.startup').unlink(),
}.items():
    try:
        operation()
        result[name] = False
    except OSError:
        result[name] = True
alias = work / 'alias'
alias.symlink_to(lab, target_is_directory=True)
try:
    (alias / 'lab.conf').write_text('x')
    result['alias_denied'] = False
except OSError:
    result['alias_denied'] = True
sock = socket.socket(socket.AF_UNIX)
try:
    sock.connect('/var/run/docker.sock')
    result['docker_socket_denied'] = False
except OSError:
    result['docker_socket_denied'] = True
finally:
    sock.close()
result['work_writable'] = (work / 'ok').write_text('ok') == 2
print(json.dumps(result))
'''
            probe = call('sbx', 'exec', '-u', 'nobody', name, 'setpriv', '--no-new-privs',
                         'python3', '-c', code, str(lab), str(work))
            assert probe.returncode == 0, probe.stderr
            data = json.loads(probe.stdout)
            assert data['uid'] != 0 and all(value is True for key, value in data.items() if key != 'uid'), data
            # Inspect only server names/status; do not print config or credentials.
            mcp = call('sbx', 'exec', '-u', 'nobody', name, 'setpriv', '--no-new-privs',
                       'codex', '-c', 'mcp_servers.mcp-gateway.enabled=false', 'mcp', 'list', '--json')
            assert mcp.returncode == 0, 'Codex MCP configuration check failed'
            servers = json.loads(mcp.stdout)
            assert all(not entry.get('enabled', False) for entry in servers), 'An MCP server remains enabled'
            login = call('sbx', 'exec', '-u', 'nobody', name, 'setpriv', '--no-new-privs', 'codex', 'login', 'status')
            assert login.returncode == 0, 'Codex login status failed for the restricted user'
            assert (lab / 'lab.conf').read_text() == 'baseline\n'
            assert (lab / 'sub').is_dir()
            assert (lab / 'r1.startup').read_text() == 'startup\n'
        finally:
            if result.returncode == 0:
                cleanup = call('sbx', 'rm', '--force', name)
                assert cleanup.returncode == 0, cleanup.stderr


def test_production_gate_session_preflight_and_transition():
    """Real production launcher; deterministic, no model invocation."""
    from types import SimpleNamespace
    from benchmark_core.docker_sandbox_runner import ProtectedCodexSession
    with tempfile.TemporaryDirectory(prefix='tesi-recovery-',dir='/private/tmp') as directory:
        root=Path(directory); root.chmod(0o755)
        lab=root/'lab'; lab.mkdir(); (lab/'lab.conf').write_text('baseline\n')
        state=root/'state'; logs=root/'logs'
        session=ProtectedCodexSession(workspace=lab,state=state,logs=logs,
                                     config=SimpleNamespace(model=lambda:None,reasoning_effort=lambda:None))
        try:
            session.create(readonly=True)
            probe=json.loads((logs/'isolation_protected.json').read_text())
            assert probe['secure'] and probe['lab_errno']==30
            assert 'CapBnd:\t0000000000000000' in probe['status']
            session.close()
            session.create(readonly=False)
            assert json.loads((logs/'isolation_writable.json').read_text())['secure']
            assert (lab/'lab.conf').read_text()=='baseline\n'
        finally:
            session.close()
        assert all(c['ok'] for c in session.cleanup)
