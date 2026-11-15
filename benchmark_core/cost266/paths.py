"""COST266 run locations; logical identities remain in the legacy format."""
from pathlib import Path

from .protocol import execution_mode, safe_path


def new_run_path(root, spec, cell):
    return safe_path(Path(root) / 'runs' / 'cost266' / cell.experiment_id / cell.dns_tree /
                     cell.prompt_type / execution_mode(spec.protocol, cell.strategy) /
                     cell.skill_mode / f'r{cell.repetition:03d}')


def resolve_run_path(root, spec, cell):
    new = new_run_path(root, spec, cell)
    old = safe_path(Path(root) / 'runs' / cell.relative)
    if cell.strategy == 'incremental':
        other_mode = 'incremental_isolated' if spec.protocol.endswith('_v2') else 'incremental_continuous'
        other = safe_path(new.parent.parent.parent / other_mode / cell.skill_mode / new.name)
        if other.exists():
            raise ValueError(f'Condizioni incompatibili: identità già usata da un altro protocollo: {other}')
    if new.exists() and old.exists():
        raise ValueError(f'Run presente nei percorsi nuovo e legacy; risolvere il conflitto: {new}, {old}')
    return old if old.exists() else new


def manifest_paths(root):
    runs = Path(root) / 'runs'
    patterns = ('*/*/*/cost266/*/*/*/r*/manifest.json',
                'cost266/*/*/*/*/*/r*/manifest.json')
    return sorted({path for pattern in patterns for path in runs.glob(pattern)})


def logical_relative(root, run):
    """Return the historical identity and optional physical execution mode."""
    parts = Path(run).relative_to(Path(root) / 'runs').parts
    if len(parts) == 7 and parts[0] == 'cost266':
        _, experiment, dns, prompt, mode, skill, repetition = parts
        if mode not in ('one_shot', 'incremental_isolated', 'incremental_continuous'):
            raise ValueError('Execution mode nel percorso non valida')
        strategy = 'one_shot' if mode == 'one_shot' else 'incremental'
        return Path(experiment, 'cost266', dns, 'cost266', prompt, strategy, skill, repetition), mode
    if len(parts) != 8:
        raise ValueError('Percorso COST266 non valido')
    return Path(*parts), None
