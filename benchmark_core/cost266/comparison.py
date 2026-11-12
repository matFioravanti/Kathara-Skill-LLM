"""Confronto esplicito delle condizioni, anche fra osservazioni v1/v2."""
from .protocol import execution_mode

FIELDS = ('baseline_sha256','correction_sha256','inventory_sha256','agent','model',
          'reasoning_effort','skill_mode','skill_protocol','skill_bundles','budgets',
          'config_sha256','component_versions','oracle_coverage_sha256')


def comparison_mismatches(left: dict, right: dict) -> list[str]:
    """Non deduce equivalenza da strategy, experiment_id o nome laboratorio.

    Protocollo/sessione sono il trattamento confrontato; tutte le altre
    condizioni devono essere note e uguali. Non unisce risultati su disco.
    """
    a,b = left.get('conditions'),right.get('conditions')
    if not isinstance(a,dict) or not isinstance(b,dict):
        return ['conditions non verificabili']
    differences=[]
    for field in FIELDS:
        # Copertura aggiuntiva può essere assente nelle fixture/historical;
        # la correction canonica è comunque obbligatoria e confrontata sopra.
        optional = field=='oracle_coverage_sha256'
        if not optional and (field not in a or field not in b):
            differences.append(field+' non verificabile')
        elif a.get(field)!=b.get(field):
            differences.append(field)
        elif field in ('baseline_sha256','correction_sha256','inventory_sha256','model','agent','reasoning_effort') and not a.get(field):
            differences.append(field+' non verificabile')
    if not left.get('prompt_type') or left.get('prompt_type')!=right.get('prompt_type'):
        differences.append('prompt_type')
    requirements_a,requirements_b=left.get('requirements_sha256'),right.get('requirements_sha256')
    if requirements_a and requirements_b:
        if requirements_a!=requirements_b:
            differences.append('requirements_sha256')
    elif not (a.get('inventory_sha256') and a.get('inventory_sha256')==b.get('inventory_sha256')
              and a.get('implementation_sha256') and a.get('implementation_sha256')==b.get('implementation_sha256')):
        differences.append('requisiti DNS storici non verificabili')
    for metadata,conditions in ((left,a),(right,b)):
        try:
            mode=execution_mode(conditions['protocol'],metadata['strategy'])
        except (ValueError,KeyError):
            differences.append('protocollo/modalità non verificabili')
            continue
        if metadata.get('execution_mode',mode)!=mode:
            differences.append('execution_mode incoerente')
    return differences
