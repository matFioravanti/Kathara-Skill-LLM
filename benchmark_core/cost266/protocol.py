"""Identità dedicata: non amplia le triple autorizzate del catalogo legacy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re

import yaml

from ..prompts import PROMPT_TYPES
from ..skill_modes import SKILL_MODE_CHOICES, mode_details
from ..skill_gate import configured_protocol, PROTOCOL
from ..workspace import manifest, tree_hash

STRATEGIES = ("one_shot", "incremental")
STAGES = ("root_hints", "tlds", "countries", "cities", "subzones_records", "resolvers_clients")
VERSION = "cost266_incremental_no_feedback_v1"
CONTINUOUS_VERSION = "cost266_incremental_continuous_session_v2"
EXECUTION_MODES = ('one_shot', 'incremental_isolated', 'incremental_continuous')


def execution_mode(protocol: str, strategy: str) -> str:
    """Etichetta descrittiva derivata, senza cambiare l'identità della run."""
    if protocol not in (VERSION, CONTINUOUS_VERSION) or strategy not in STRATEGIES:
        raise ValueError(f'Protocollo/strategia COST266 non supportati: {protocol!r}/{strategy!r}')
    if strategy == 'one_shot':
        return 'one_shot'
    return 'incremental_isolated' if protocol == VERSION else 'incremental_continuous'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def safe_path(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Link simbolico non consentito: {path}")
    return path


def clean_lab(lab: Path) -> dict:
    entries = manifest(safe_path(lab))
    for name, entry in entries.items():
        parts = Path(name).parts
        if entry['kind'] == 'link' or any(p in ('.codex', '.git', '.agents', 'evaluation', 'logs') for p in parts):
            raise ValueError(f"Stato estraneo o link nel laboratorio: {name}")
        if Path(name).name in ('correction.yaml', 'correction.yml') or name.endswith(('.eval', '.jsonl')):
            raise ValueError(f"Artefatto valutatore/sessione nel laboratorio: {name}")
    return entries


@dataclass(frozen=True)
class Spec:
    experiment_id: str
    dataset: Path
    strategies: tuple[str, ...]
    prompt_types: tuple[str, ...]
    skill_modes: tuple[str, ...]
    repetitions: int
    stage_timeout: int
    total_timeout: int
    checker_timeout: int
    source: Path
    protocol: str = VERSION


@dataclass(frozen=True)
class Cell:
    experiment_id: str
    prompt_type: str
    strategy: str
    skill_mode: str
    repetition: int
    scenario: str = 'cost266'
    dns_tree: str = 'multitld_v2'

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.experiment_id):
            raise ValueError('experiment_id non valido')
        if (self.scenario, self.dns_tree) != ('cost266', 'multitld_v2'):
            raise ValueError('Identità COST266 non autorizzata')
        if self.prompt_type not in PROMPT_TYPES or self.strategy not in STRATEGIES or self.skill_mode not in SKILL_MODE_CHOICES:
            raise ValueError('Cella COST266 non valida')
        if type(self.repetition) is not int or self.repetition < 1:
            raise ValueError('repetition non valida')

    @property
    def relative(self) -> Path:
        return Path(self.experiment_id, self.scenario, self.dns_tree, 'cost266', self.prompt_type,
                    self.strategy, self.skill_mode, f'r{self.repetition:03d}')

    @property
    def run_id(self) -> str:
        return '__'.join(self.relative.parts)


def load_spec(path: Path, root: Path) -> Spec:
    data = yaml.safe_load(safe_path(path).read_text())
    required = {'experiment', 'dataset', 'strategies', 'prompt_types', 'skill_modes', 'repetitions', 'budgets', 'protocol'}
    if not isinstance(data, dict) or set(data) != required or data['protocol'] not in (VERSION, CONTINUOUS_VERSION):
        raise ValueError('Configurazione COST266 non valida o protocollo non supportato')
    if not isinstance(data['experiment'], dict) or set(data['experiment']) != {'id'}:
        raise ValueError('experiment deve contenere solo id')
    for key, allowed in (('strategies', STRATEGIES), ('prompt_types', PROMPT_TYPES), ('skill_modes', SKILL_MODE_CHOICES)):
        values = data[key]
        if not isinstance(values, list) or not values or any(v not in allowed for v in values) or len(set(values)) != len(values):
            raise ValueError(f'{key} non valido')
    budgets = data['budgets']
    if not isinstance(budgets, dict) or set(budgets) != {'stage_seconds', 'total_seconds', 'checker_seconds'}:
        raise ValueError('budgets non validi')
    for value in [data['repetitions'], *budgets.values()]:
        if type(value) is not int or value < 1:
            raise ValueError('Budget e repetitions devono essere interi positivi')
    Cell(data['experiment']['id'], data['prompt_types'][0], data['strategies'][0], data['skill_modes'][0], 1)
    if not isinstance(data['dataset'], str) or not data['dataset'].strip():
        raise ValueError('dataset deve essere un percorso non vuoto')
    if '..' in Path(data['dataset']).parts:
        raise ValueError('dataset non può contenere traversal')
    dataset = safe_path(root / data['dataset'])
    if not dataset.is_relative_to(root / 'experiments'):
        raise ValueError('dataset deve risiedere sotto experiments/')
    return Spec(data['experiment']['id'], dataset, tuple(data['strategies']), tuple(data['prompt_types']),
                tuple(data['skill_modes']), data['repetitions'], budgets['stage_seconds'], budgets['total_seconds'],
                budgets['checker_seconds'], path, data['protocol'])


def cells(spec: Spec):
    for prompt in spec.prompt_types:
        for mode in spec.skill_modes:
            for repetition in range(1, spec.repetitions + 1):
                for strategy in spec.strategies:
                    yield Cell(spec.experiment_id, prompt, strategy, mode, repetition)


def validate_backend(config, mode: str, *, strategy=None, protocol=VERSION):
    agent = config.data['aut']['agent']
    backend = config.data.get('docker_sandbox', {}).get('execution_backend')
    if backend not in (None, 'host', 'codex_cli', 'antigravity_cli', 'docker_sandbox'):
        raise ValueError(f'Backend non supportato: {backend}; nessun fallback')
    if agent not in ('codex', 'antigravity') or (agent != 'codex' and (mode != 'no_skill' or backend == 'docker_sandbox')):
        raise ValueError('Backend/agente/Skill incompatibili')
    if (agent=='codex' and backend=='antigravity_cli') or (agent=='antigravity' and backend=='codex_cli'):
        raise ValueError('Backend/agente incompatibili: nessun fallback')
    if protocol == CONTINUOUS_VERSION and strategy == 'incremental':
        if agent != 'codex' or backend != 'docker_sandbox':
            raise ValueError('La sessione continua v2 richiede Codex e docker_sandbox: nessun fallback')
    if agent == 'codex' and configured_protocol(config) == PROTOCOL and mode_details(mode).forced_skills:
        from ..skill_gate import recovery_enabled
        if protocol == CONTINUOUS_VERSION and backend == 'docker_sandbox' and recovery_enabled(config):
            return
        raise ValueError('enforced_read_v1 usa più chiamate/sandbox: incompatibile con una chiamata AUT per fase. '
                         'Selezionare esplicitamente un config con explicit_read_v2 oppure no_skill/auto; nessun downgrade automatico.')


COMMON = ('Configura i file DNS del laboratorio esistente. Non avviare Kathara. '
          'Conserva dispositivi, interfacce, indirizzi, rotte e tutte le righe startup esistenti; '
          'aggiungi solo configurazione DNS e riavvio named. Autoritativi senza ricorsione, resolver senza zone autoritative. '
          'Nessun forwarder Internet; DNSSEC validation disabilitata. IPv4 soltanto. '
          'Le assegnazioni sotto autorizzano esplicitamente più zone sul medesimo server. '
          'Completa soltanto le nuove richieste elencate e conserva il lavoro già presente.')


def stage_requirements(inventory: dict) -> list[list[dict]]:
    result = [[] for _ in STAGES]
    zones = {z['name']: z for z in inventory['zones']}
    for zone in inventory['zones']:
        stage = zone['stage'] - 1
        result[stage].append({'request': 'authoritative_zone', **zone})
        if zone['parent']:
            parent = zones[zone['parent']]
            result[stage].append({'request': 'delegation_and_glue', 'parent': parent['name'],
                                  'parent_device': parent['device'], 'parent_address': parent['address'],
                                  'child': zone['name'], 'ns': zone['ns'], 'address': zone['address']})
        for record in zone.get('records', []):
            result[4].append({'request': 'record', 'zone': zone['name'], 'device': zone['device'], **record})
    root = zones['.']
    for resolver in inventory['resolvers']:
        result[0].append({'request': 'root_hints', **resolver, 'root_ns': root['ns'], 'root_address': root['address']})
        result[5].append({'request': 'recursive_resolver', **resolver, 'root_ns': root['ns'], 'root_address': root['address'],
                          'allow_recursion': 'all_lab_clients', 'authoritative_zones': []})
    for client in inventory['clients']:
        result[5].append({'request': 'client_resolver_and_resolution', **client, 'queries': inventory['queries']})
    return result


def render(requirements: list[dict], prompt_type: str) -> str:
    # Stesso contenuto fattuale; cambia la rappresentazione, mai le risorse legacy T1..T6.
    def sentence(item):
        return '; '.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in item.items()) + '.'
    if prompt_type == 'T6':
        body = json.dumps({'requirements': requirements}, indent=2, ensure_ascii=False)
    elif prompt_type == 'T5':
        body = '\n'.join(('└── ' if i == len(requirements)-1 else '├── ') + sentence(item) for i, item in enumerate(requirements))
    elif prompt_type == 'T1':
        body = '\n'.join('- ' + sentence(item) for item in requirements)
    elif prompt_type == 'T2':
        body = '\n\n'.join('È richiesto quanto segue: ' + sentence(item) for item in requirements)
    elif prompt_type == 'T3':
        body = '\n\n'.join('Prepara questa parte della rete dei nomi: ' + sentence(item) for item in requirements)
    elif prompt_type == 'T4':
        body = ' '.join(sentence(item) for item in requirements)
    else:
        raise ValueError('prompt_type non valido')
    return COMMON + '\n\n' + body + '\n'


def prompts(inventory: dict, cell: Cell) -> list[str]:
    requirements = stage_requirements(inventory)
    selected = [sum(requirements, [])] if cell.strategy == 'one_shot' else requirements
    return [render(r, cell.prompt_type) for r in selected]
