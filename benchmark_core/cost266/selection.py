"""Selezione host della configurazione e delle celle; nessun motore AUT."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..skill_modes import SKILL_MODE_CHOICES
from .protocol import (CONTINUOUS_VERSION, VERSION, EXECUTION_MODES, Spec,
                       cells, execution_mode, load_spec)

MODE_STRATEGIES = {'one_shot':'one_shot', 'incremental_isolated':'incremental',
                   'incremental_continuous':'incremental'}
MODE_PROTOCOLS = {'one_shot':CONTINUOUS_VERSION, 'incremental_isolated':VERSION,
                  'incremental_continuous':CONTINUOUS_VERSION}


@dataclass(frozen=True)
class Selection:
    spec: Spec
    mode: str | None
    strategy: str | None
    explicit_experiment: bool

    def selected_cells(self, *, prompt_type=None, skill_mode=None, repetition=None):
        matrix_spec = self.spec
        # Con il nuovo selettore e il piano predefinito, una Skill esplicitamente
        # richiesta sceglie il trattamento della singola run. Non modifica il
        # file YAML né i percorsi Skill. Senza --execution-mode restano i filtri
        # storici; un file sperimentale esplicito conserva i propri vincoli.
        if self.mode and skill_mode:
            if skill_mode not in SKILL_MODE_CHOICES:
                raise ValueError(f'Skill mode non valida: {skill_mode}')
            if self.explicit_experiment and skill_mode not in self.spec.skill_modes:
                raise ValueError(f'La configurazione esplicita non abilita la Skill mode {skill_mode}')
            if not self.explicit_experiment:
                matrix_spec = replace(self.spec, skill_modes=(skill_mode,))
        return [cell for cell in cells(matrix_spec) if
                (not self.strategy or cell.strategy==self.strategy) and
                (not prompt_type or cell.prompt_type==prompt_type) and
                (not skill_mode or cell.skill_mode==skill_mode) and
                (repetition is None or cell.repetition==repetition)]


def resolve_selection(root: Path, config_root: Path, experiment: Path | None = None,
                      mode: str | None = None, strategy: str | None = None, *, loader=None) -> Selection:
    """Carica il piano corretto prima di dataset, celle, preflight e sandbox."""
    if mode is not None and mode not in EXECUTION_MODES:
        raise ValueError(f'Execution mode non valida: {mode}')
    if mode and strategy and strategy!=MODE_STRATEGIES[mode]:
        raise ValueError(f'Argomenti contraddittori: --execution-mode {mode} e --strategy {strategy}')
    explicit = experiment is not None
    name = 'cost266_v1.yaml' if mode=='incremental_isolated' else 'cost266.yaml'
    path = experiment if explicit else root/'experiments'/name
    spec = (loader or load_spec)(path,config_root)
    if mode:
        required = MODE_PROTOCOLS[mode]
        # Eccezione esplicita prevista: il one-shot v1 resta accessibile con
        # la sua configurazione legacy, senza sostituirne protocollo/id/dataset.
        legacy_one_shot = explicit and mode=='one_shot' and spec.protocol==VERSION
        if spec.protocol!=required and not legacy_one_shot:
            raise ValueError(f'Configurazione incompatibile con --execution-mode {mode}: '
                             f'protocollo {spec.protocol}; atteso {required}. File preservato: {path}')
        strategy = MODE_STRATEGIES[mode]
        if strategy not in spec.strategies:
            raise ValueError(f'La configurazione {path} non abilita la strategia {strategy}')
    return Selection(spec,mode,strategy,explicit)


def describe_cell(spec: Spec, cell) -> str:
    mode = execution_mode(spec.protocol,cell.strategy)
    session = {'one_shot':'single_task','incremental_isolated':'independent',
               'incremental_continuous':'persistent'}[mode]
    sandbox = {'one_shot':'single_functional_task','incremental_isolated':'per_stage',
               'incremental_continuous':'shared'}[mode]
    return '\n'.join((f'Execution mode: {mode}',f'Protocol: {spec.protocol}',
        f'Experiment: {spec.experiment_id}',f'Prompt type: {cell.prompt_type}',
        f'Skill mode: {cell.skill_mode}',f'Repetition: {cell.repetition}',
        f'Functional turns: {1 if cell.strategy=="one_shot" else 6}',
        f'Session policy: {session}',f'Writable sandbox policy: {sandbox}','Checker: final'))
