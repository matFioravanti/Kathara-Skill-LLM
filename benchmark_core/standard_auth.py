"""Official Codex app-server refresh only; no tokens or account data are logged."""
import json
import os
import selectors
import subprocess
import time

from .codex_cli_runner import codex_environment, codex_executable


def refresh_account(timeout=30):
    """Return True only for a managed ChatGPT account after a refresh request.

    Unsupported CLI versions, revoked sessions and external-token providers return
    False. No model turn, logout, browser login or auth.json parsing is performed.
    """
    process = None
    selector = selectors.DefaultSelector()
    try:
        process=subprocess.Popen([codex_executable(),'app-server'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=codex_environment(),start_new_session=True)
        selector.register(process.stdout,selectors.EVENT_READ)
        pending=b''; deadline=time.monotonic()+timeout
        def send(message):
            process.stdin.write((json.dumps(message)+'\n').encode()); process.stdin.flush()
        def response(identifier):
            nonlocal pending
            while time.monotonic()<deadline:
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1)
                    msg=json.loads(line)
                    if msg.get('id')==identifier: return msg.get('result') if 'error' not in msg else None
                events=selector.select(max(0,deadline-time.monotonic()))
                if not events: return None
                chunk=os.read(process.stdout.fileno(),65536)
                if not chunk: return None
                pending+=chunk
                if len(pending)>1048576: return None
            return None
        send({'id':0,'method':'initialize','params':{'clientInfo':{'name':'tesi_skill','version':'1.0.0'}}})
        if response(0) is None: return False
        send({'method':'initialized','params':{}})
        send({'id':1,'method':'account/read','params':{'refreshToken':True}})
        result=response(1)
        return bool(isinstance(result,dict) and isinstance(result.get('account'),dict)
                    and result['account'].get('type')=='chatgpt')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        return False
    finally:
        selector.close()
        if process is not None:
            if process.stdin: process.stdin.close()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            if process.stdout: process.stdout.close()
