"""Real Docker Sandbox mount comparison, without model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_SBX_ISOLATION_TESTS') != '1',
                                reason='requires explicit opt-in and local sbx daemon')


def invoke(*args):
    return subprocess.run(args, text=True, capture_output=True, timeout=180, check=False)


def digest(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        h.update(p.relative_to(root).as_posix().encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_comparative_read_write_and_read_only_mounts():
    with tempfile.TemporaryDirectory(prefix='tesi-mount-', dir='/private/tmp') as directory:
        root = Path(directory)
        root.chmod(0o755)
        names = []
        try:
            outcomes = {}
            for mode in ('rw', 'ro'):
                work, lab = root / ('work_' + mode), root / ('lab_' + mode)
                work.mkdir(mode=0o777); work.chmod(0o777)
                lab.mkdir(mode=0o777); lab.chmod(0o777)
                (lab / 'sub').mkdir(mode=0o777); (lab / 'sub').chmod(0o777)
                for file, contents in (('lab.conf', 'baseline\n'), ('r1.startup', 'startup\n'), ('delete.txt', 'delete\n')):
                    (lab / file).write_text(contents); (lab / file).chmod(0o666)
                before = digest(lab)
                name = 'tesi-mount-' + mode + '-' + uuid.uuid4().hex[:10]
                names.append(name)
                create = invoke('sbx', 'create', 'codex', str(work), str(lab) + (':ro' if mode == 'ro' else ''),
                                '--name', name, '--skills', 'off', '--pull', 'missing')
                assert create.returncode == 0, create.stderr
                code = r'''
import os, pathlib, socket, subprocess, sys, json
lab, work = map(pathlib.Path, sys.argv[1:])
r = {'read': (lab/'lab.conf').read_text() == 'baseline\n', 'uid': os.getuid()}
r['shell_write'] = subprocess.run(['sh','-c','echo shell > "$1/lab.conf"','sh',str(lab)], capture_output=True).returncode == 0
for name, f in {'python_write': lambda: (lab/'lab.conf').write_text('python\n'),
                'startup_write': lambda: (lab/'r1.startup').write_text('changed\n'),
                'create': lambda: (lab/'new.txt').write_text('new'),
                'delete': lambda: (lab/'delete.txt').unlink()}.items():
    try: f(); r[name] = True
    except OSError: r[name] = False
for name, f in {'chmod': lambda: (lab/'lab.conf').chmod(0o777),
                'chown': lambda: os.chown(lab/'lab.conf', os.getuid(), os.getgid())}.items():
    try: f(); r[name] = True
    except OSError: r[name] = False
alias = work/'alias'; alias.symlink_to(lab, target_is_directory=True)
try: (alias/'lab.conf').write_text('alias\n'); r['alias_write'] = True
except OSError: r['alias_write'] = False
r['remount'] = subprocess.run(['mount','-o','remount,rw',str(lab)], capture_output=True).returncode == 0
sock = socket.socket(socket.AF_UNIX)
try: sock.connect('/var/run/docker.sock'); r['docker_socket'] = True
except OSError: r['docker_socket'] = False
finally: sock.close()
r['work_write'] = (work/'ok').write_text('ok') == 2
st = pathlib.Path('/proc/self/status').read_text()
r['no_new_privileges'] = 'NoNewPrivs:\t1' in st
r['zero_capabilities'] = 'CapEff:\t0000000000000000' in st
print(json.dumps(r))
'''
                run = invoke('sbx', 'exec', '-u', 'nobody', name, 'setpriv', '--no-new-privs',
                             'python3', '-c', code, str(lab), str(work))
                assert run.returncode == 0, run.stderr
                outcome = json.loads(run.stdout); outcomes[mode] = outcome
                assert outcome['uid'] != 0 and all(outcome[k] for k in ('read', 'work_write', 'no_new_privileges', 'zero_capabilities'))
                assert not outcome['remount'] and not outcome['docker_socket']
                keys = ('shell_write', 'python_write', 'startup_write', 'create', 'delete', 'alias_write')
                assert all(outcome[key] == (mode == 'rw') for key in keys), outcome
                if mode == 'ro':
                    assert not outcome['chmod'] and not outcome['chown']
                    assert digest(lab) == before
                else:
                    assert digest(lab) != before
            assert outcomes['rw']['uid'] == outcomes['ro']['uid']
        finally:
            for name in names:
                removed = invoke('sbx', 'rm', '--force', name)
                assert removed.returncode == 0 or 'not found' in removed.stderr.lower(), f'cleanup failed for {name}: {removed.stderr}'
