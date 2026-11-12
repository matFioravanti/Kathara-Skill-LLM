"""Shared report destinations and conservative COST266 publication checks."""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile


def results_root(config):
    return config.path(config.data['results']['directory'])


def _component(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',value):
        raise ValueError('Identificativo report non valido')
    return value


def general_root(config):return results_root(config)/'general'
def general_experiment(config,experiment_id):
    experiment_id=_component(experiment_id)
    if experiment_id=='_legacy':raise ValueError('ID _legacy riservato ai report legacy')
    return general_root(config)/experiment_id
def general_legacy(config):return general_root(config)/'_legacy'
def cost266_experiment(config,experiment_id):return results_root(config)/'cost266'/'experiments'/_component(experiment_id)
def cost266_comparison(config,comparison_id):return results_root(config)/'cost266'/'comparisons'/_component(comparison_id)


def is_cost266_manifest(manifest):
    if not isinstance(manifest,dict):return False
    schema=manifest.get('schema')
    conditions=manifest.get('conditions')
    protocol=conditions.get('protocol') if isinstance(conditions,dict) else None
    return (isinstance(schema,str) and schema.startswith('cost266_')
            or manifest.get('task_level')=='cost266'
            or isinstance(protocol,str) and protocol.startswith('cost266_'))


COST_FILES=('runs.csv','checks.csv','summary.csv','stages.csv','pairs.csv','benchmark.xlsx','report_manifest.json')
MARKER='.cost266_report_owner.json'


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_cost266_report_destination(output):
    """Never replace a file without a matching marker and matching bytes."""
    output=Path(output).absolute()
    for path in (output,*output.parents):
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise ValueError(f'Percorso report non valido o occupato, preservato: {path}')
    marker=output/MARKER
    if marker.is_symlink():raise ValueError(f'Marker report non valido: {marker}')
    present=[output/name for name in COST_FILES if (output/name).exists() or (output/name).is_symlink()]
    if not marker.exists():
        if present:raise ValueError(f'Report COST266 non gestito, preservato: {present[0]}')
        return
    try:
        data=json.loads(marker.read_text())
        hashes=data['sha256']
        if (data.get('schema')!='cost266_report_owner_v1' or data.get('experiment_id')!=output.name
                or set(hashes)!=set(COST_FILES)):raise ValueError()
        for name in COST_FILES:
            path=output/name
            if path.is_symlink() or not path.is_file() or _digest(path)!=hashes[name]:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise ValueError(f'Report COST266 non gestito o alterato, preservato: {output}') from None


def publish_cost266_report(root,output):
    from .cost266.reports import aggregate_cost266
    root=Path(root).resolve()
    raw=Path(output).absolute()
    if any(path.is_symlink() for path in (raw,*raw.parents)):
        raise ValueError(f'Link simbolico non consentito nel percorso report: {raw}')
    output=Path(os.path.abspath(raw))
    if output==root or output.is_relative_to(root/'runs') or output.is_relative_to(root/'experiments'):
        raise ValueError(f'Directory report non consentita: {output}')
    validate_cost266_report_destination(output)
    result=aggregate_cost266(root,output)
    data={'schema':'cost266_report_owner_v1','experiment_id':output.name,
          'sha256':{name:_digest(output/name) for name in COST_FILES}}
    fd,tmp=tempfile.mkstemp(prefix='.cost266-owner-',dir=output)
    try:
        with os.fdopen(fd,'w') as stream:json.dump(data,stream,sort_keys=True,indent=2)
        os.replace(tmp,output/MARKER)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return result
