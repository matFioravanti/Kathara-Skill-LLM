"""Ciclo di vita v2: un workspace, un thread e una sandbox scrivibile.

Riusa il launcher protetto e il gate standard; nessuna credenziale, rete o
sessione è ricostruita da questo modulo. I checkpoint sono copie solo host.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import time

from ..docker_sandbox_runner import ProtectedCodexSession, sbx_get_sandbox_id, SandboxExecutionError
from ..inspect_adapter import create_inspect_eval_log
from ..inspect_runner import validate_aut_workspace_isolation
from ..run_metrics import codex_usage
from ..skill_gate import enforce_or_block, recovery_enabled, run_recovery_gate
from ..skill_modes import mode_details, prepare_skill_workspace, source_paths, execution_prompt
from ..workspace import copy_lab, manifest, manifest_hash, tree_hash, write_json


class TrackedSession:
    """Osserva create/close senza sostituire le verifiche del launcher."""

    def __init__(self, owner, **kwargs):
        self.owner = owner
        self.inner = ProtectedCodexSession(**kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def create(self, *, readonly):
        entry = {'readonly':readonly, 'name':None, 'id':None, 'created':False, 'cleanup_ok':None}
        self.owner.environments.append(entry)
        try:
            self.inner.create(readonly=readonly)
            entry.update(name=self.inner.name, id=sbx_get_sandbox_id(self.inner.name), created=True)
            if not entry['id']:
                raise SandboxExecutionError('Identità sandbox non verificabile')
        finally:
            entry['name'] = self.inner.name
            if entry['name'] and not entry['id']:
                # Anche un create/probe fallito può avere già allocato un ambiente.
                entry['id'] = sbx_get_sandbox_id(entry['name'])
                if entry['id']:
                    entry['created'] = True
            entry['creation_unknown'] = bool(entry['name']) and not entry['created']

    def close(self):
        name = self.inner.name
        try:
            self.inner.close()
        finally:
            if name:
                for entry in self.owner.environments:
                    if entry['name'] == name:
                        entry['cleanup_ok'] = bool(self.inner.cleanup and self.inner.cleanup[-1]['ok'])


class ContinuousAutSession:
    def __init__(self, config, run: Path, mode: str, timeout_provider):
        self.config, self.run, self.mode = config, run, mode
        self.timeout_provider = timeout_provider
        self.environments = []
        self.session = None
        self.workspace = None
        self.writable = None
        self.thread_id = None
        self.continuity = True
        self.observed_threads = set()
        self.stage_state = {}
        self.skill_sources = source_paths(config, mode_details(mode).available_skills)
        self.bundle_hashes = {name:tree_hash(path.parent) for name,path in self.skill_sources.items()}
        self.gated = recovery_enabled(config) and bool(mode_details(mode).forced_skills)
        self.logs = run/'logs/aut'
        self.started = None

    def _factory(self, **kwargs):
        self.session = TrackedSession(self, **kwargs)
        return self.session

    def _verify_skills(self):
        if tree_hash(self.workspace/'.codex') != self.skills_hash:
            raise SandboxExecutionError('Skill/configurazione .codex del workspace alterata')
        if any(tree_hash(path.parent) != self.bundle_hashes[name] for name,path in self.skill_sources.items()):
            raise SandboxExecutionError('Bundle Skill canonico alterato')

    def _enter_writable(self, session, body):
        self.session = session
        candidates = [e for e in self.environments if e['created'] and not e['readonly']]
        if len(candidates) != 1:
            raise SandboxExecutionError('Attesa una sola sandbox scrivibile')
        self.writable = candidates[0]
        self.thread_id = session.thread_id
        if self.gated and not self.thread_id:
            raise SandboxExecutionError('Thread del gate perduto prima della fase scrivibile')
        if self.gated:
            protected = [result for directory,result in session.turns
                         if directory==self.logs/'phase_a' or directory==self.logs/'fallback'
                         or directory.parent==self.logs/'retries']
            if not protected or protected[-1].get('session_id') != self.thread_id:
                self.continuity = False
                raise SandboxExecutionError('Thread cambiato nella transizione protetta/scrivibile')
        if self.thread_id:
            self.observed_threads.add(self.thread_id)
        self._verify_identity()
        body(self)

    def _verify_identity(self):
        if (self.session.name != self.writable['name'] or self.session.readonly
                or sbx_get_sandbox_id(self.session.name) != self.writable['id']
                or (self.thread_id is not None and self.session.thread_id != self.thread_id)):
            self.continuity = False
            raise SandboxExecutionError('Identità sandbox/thread cambiata: continuità perduta')

    def snapshot(self, target: Path):
        """Copia il lab, lasciando .codex intatta nel workspace vivo."""
        from .protocol import clean_lab
        self._verify_skills()
        before = manifest(self.workspace)
        if any(entry['kind']=='link' for entry in before.values()):
            raise SandboxExecutionError('Link simbolico nel workspace AUT')
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.workspace, target, dirs_exist_ok=True, symlinks=True,
                        ignore=lambda directory,names: ['.codex'] if Path(directory)==self.workspace else [])
        clean_lab(target)
        if before != manifest(self.workspace):
            raise SandboxExecutionError('Workspace mutato durante lo snapshot')
        self._verify_skills()

    def stage_fields(self, index: int, prompt: str):
        from .protocol import digest
        return {'stage_index':index, 'stage_prompt_sha256':digest(prompt.encode()),
                'sandbox_name':self.writable['name'], 'sandbox_id':self.writable['id'],
                'thread_id':self.thread_id, 'session_count':len(self.observed_threads),
                'sandbox_count':sum(e['created'] for e in self.environments),
                'writable_sandbox_count':1, 'context_continuity_verified':self.continuity,
                'stage_completed':False, 'skill_gate_inherited':self.gated}

    def turn(self, attempt: Path, stage_id: str, prompt: str, index: int, timeout: int):
        logs = attempt/'logs/aut'
        self.stage_state = self.stage_fields(index,prompt)
        # Il gate ha già caricato le Skill; il compito funzionale conserva i byte originali.
        actual = prompt if self.gated else execution_prompt(self.mode,prompt)
        (logs/'prompt_sent.md').write_bytes(actual.encode())
        error = None
        try:
            self._verify_identity()
            self._verify_skills()
            live = {key:value for key,value in manifest(self.workspace).items()
                    if Path(key).parts[0] != '.codex'}
            if manifest_hash(live) != tree_hash(attempt/'input/lab'):
                raise SandboxExecutionError('Workspace vivo diverso dallo stato della fase precedente')
            events,result = self.session.turn(prompt=actual.encode(),directory=logs/'turn',timeout=timeout)
            ids = [e.get('thread_id') for e in events if e.get('type')=='thread.started']
            self.observed_threads.update(value for value in ids if isinstance(value,str) and value)
            completions = [e for e in events if e.get('type')=='turn.completed']
            if (len(ids)!=1 or not isinstance(ids[0],str) or not ids[0]
                    or (self.thread_id is not None and ids[0]!=self.thread_id)
                    or self.session.thread_id!=ids[0] or len(completions)!=1
                    or any(e.get('type') in ('turn.failed','error') for e in events)
                    or result.get('returncode')!=0 or result.get('timed_out') is not False
                    or result.get('stdin_delivery_verified') is not True
                    or result.get('session_id')!=ids[0]
                    or result.get('usage')!=completions[0].get('usage')):
                self.continuity = False
                raise SandboxExecutionError('Turno incompleto o thread Codex non verificabile')
            if (logs/'turn/prompt_sent.md').read_bytes()!=actual.encode():
                raise SandboxExecutionError('Prompt stdin alterato')
            self.thread_id = ids[0]
            self._verify_identity()
            self._verify_skills()
            if self.gated and index==1:
                # Evidenza compatibile col verificatore recovery_v1 esistente:
                # la prima scrittura dopo il gate. Solo copia host, mai un nuovo turno.
                evidence=self.logs/'phase_b'
                evidence.mkdir(exist_ok=False)
                for path in (logs/'turn').iterdir():
                    if path.is_file() and not path.is_symlink():
                        shutil.copy2(path,evidence/path.name)
        except BaseException as exc:
            error = exc
            self.continuity = False
            raise
        finally:
            # Il launcher può conservare anche un turno parziale prima di sollevare errore.
            raw = logs/'turn'
            if raw.exists():
                for path in raw.iterdir():
                    if path.is_file() and not path.is_symlink():
                        shutil.copy2(path, logs/path.name)
                from ..run_metrics import load_jsonl
                self.observed_threads.update(e['thread_id'] for e in load_jsonl(raw/'events.jsonl')
                    if e.get('type')=='thread.started' and isinstance(e.get('thread_id'),str) and e['thread_id'])
            if not (logs/'result.json').exists():
                write_json(logs/'result.json', {'returncode':1,'timed_out':isinstance(error,TimeoutError),
                    'duration_seconds':None, 'usage':None, 'error':str(error)})
            data = json.loads((logs/'result.json').read_text())
            data['sandbox_overhead_seconds'] = 0
            write_json(logs/'result.json',data)
            self.stage_state.update(thread_id=self.thread_id,session_count=len(self.observed_threads),
                                    context_continuity_verified=self.continuity)
            write_json(logs/'sandbox_metadata.json', {**self.stage_state,'cleanup_ok':None,
                'codex_sandbox_version':self.session.version,'execution_backend':'docker_sandbox'})
            try:
                self.snapshot(attempt/'lab')
            except BaseException as snapshot_error:
                write_json(logs/'snapshot_error.json',{'error':str(snapshot_error)})
                if error is None:
                    raise
            finally:
                create_inspect_eval_log(logs=logs,run_id=stage_id,prompt=actual,agent='codex',model=self.config.model())

    def run_all(self, body):
        """Il cleanup termina prima del ritorno al runner e del checker."""
        self.started = time.monotonic()
        error = None
        try:
            with tempfile.TemporaryDirectory(prefix='cost266-continuous-') as temporary:
                self.workspace = Path(temporary)/'lab'
                copy_lab(self.run/'input/lab',self.workspace)
                validate_aut_workspace_isolation(self.workspace,self.config.root)
                prepare_skill_workspace(self.workspace,self.config,self.mode)
                self.skills_hash = tree_hash(self.workspace/'.codex')
                enforce_or_block(self.config,self.run,'codex',self.mode)
                if self.gated:
                    run_recovery_gate(config=self.config,run=self.run,workspace=self.workspace,
                        original_prompt='',mode=self.mode,session_factory=self._factory,
                        writable_phase=lambda session:self._enter_writable(session,body),
                        timeout_provider=self.timeout_provider)
                else:
                    session = self._factory(workspace=self.workspace,state=Path(temporary)/'state',
                                            logs=self.logs,config=self.config)
                    try:
                        session.create(readonly=False)
                        self._enter_writable(session,body)
                    finally:
                        session.close()
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._finish(error)

    def _finish(self, error):
        gate_turns = []
        if self.session:
            for directory,result in self.session.turns:
                if directory == self.logs/'phase_a' or directory == self.logs/'fallback' or directory.parent == self.logs/'retries':
                    gate_turns.append({'path':str(directory.relative_to(self.run)),
                        'tokens':codex_usage([{'type':'turn.completed','usage':result.get('usage')}]),
                        'agent_seconds':result.get('duration_seconds')})
            for _,result in self.session.turns:
                value = result.get('session_id')
                if value:
                    self.observed_threads.add(value)
        cleanup_ok = bool(self.environments) and all(e['cleanup_ok'] is True for e in self.environments)
        unknown = any(e.get('creation_unknown') for e in self.environments)
        fields = {'sandbox_name':self.writable['name'] if self.writable else None,
            'sandbox_id':self.writable['id'] if self.writable else None,'thread_id':self.thread_id,
            'session_count':len(self.observed_threads),'sandbox_count':None if unknown else sum(e['created'] for e in self.environments),
            'writable_sandbox_count':sum(e['created'] and not e['readonly'] for e in self.environments),
            'protected_sandbox_count':sum(e['created'] and e['readonly'] for e in self.environments),
            'context_continuity_verified':bool(self.thread_id) and len(self.observed_threads)==1 and self.continuity,
            'observed_thread_ids':sorted(self.observed_threads),
            'cleanup_ok':cleanup_ok, 'environments':self.environments,
            'overhead_seconds':self.session.overhead if self.session else None,
            'codex_sandbox_version':self.session.version if self.session else None,
            'session_wall_seconds':time.monotonic()-self.started,'execution_backend':'docker_sandbox',
            'error':f'{type(error).__name__}: {error}' if error else None}
        write_json(self.logs/'continuous_session.json',fields)
        write_json(self.logs/'sandbox_metadata.json',fields)
        write_json(self.logs/'gate_turn_metrics.json',{'turns':gate_turns})
        # Anche le letture/retry/fallback conservano un log Inspect individuale.
        for item in gate_turns:
            directory=self.run/item['path']
            prompt=(directory/'prompt_sent.md').read_text()
            create_inspect_eval_log(logs=directory,run_id=directory.name,prompt=prompt,agent='codex',model=self.config.model())
