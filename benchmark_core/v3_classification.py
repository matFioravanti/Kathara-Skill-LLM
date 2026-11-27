"""Map custom checker results to codes documented in the correction snapshot."""
import re

import yaml

from .check_classification import classify

CODE_CATEGORIES = {
    'DNS_AUTH_SOA_ROLE': ('dns_soa', 'SOA'),
    'DNS_DELEGATION_NS_GLUE': ('dns_delegation', 'NS'),
    'DNS_AUTH_A_RECORD': ('dns_record', 'A'),
    'DNS_AUTH_MX_RECORD': ('dns_record', 'MX'),
    'DNS_RECURSION_SELF': ('dns_recursion', None),
    'DNS_RESOLVER_LAB_ROOT': ('dns_resolver', None),
    'DNS_ROOT_NS_ADDRESS': ('dns_authority', None),
    'DNS_AUTH_ZONE_EXCLUSIVITY': ('dns_authority', 'SOA'),
    'DNS_CLIENT_RECURSION': ('dns_recursion', None),
    'DNS_TCP_RECURSION': ('dns_recursion', None),
    'DNS_RECURSIVE_A_RECORD': ('dns_resolution', 'A'),
    'DNS_RECURSIVE_MX_RECORD': ('dns_record', 'MX'),
}
CLASS_FIELDS = ['test_code', 'device', 'primary_category', 'subcategory',
                'record_type', 'classification_source']


def correction_codes(content):
    """Index by exact device and command; comments label their following YAML entry."""
    text = content.decode('utf-8')
    lines = text.splitlines()
    node = yaml.compose(text)

    def mapping(node):
        return {key.value: value for key, value in node.value} if isinstance(node, yaml.MappingNode) else {}

    custom = mapping(mapping(mapping(node).get('test')).get('custom_commands'))
    index = {}
    for device, entries in custom.items():
        if not isinstance(entries, yaml.SequenceNode):
            continue
        for entry in entries.value:
            command = mapping(entry).get('command')
            if not isinstance(command, yaml.ScalarNode):
                continue
            preceding = entry.start_mark.line - 1
            while preceding >= 0 and not lines[preceding].strip():
                preceding -= 1
            comment = lines[preceding] if preceding >= 0 else ''
            match = re.fullmatch(r'\s*#\s*(DNS_[A-Z0-9_]+)\s+-\s+(.+)', comment)
            if not match:
                continue
            key = (device, command.value)
            code = match.group(1)
            # Multiple contradictory labels must never silently choose a category.
            if key in index and index[key] != code:
                raise ValueError(f'Codici ambigui per un comando su {device}')
            index[key] = code
    return index


def classify_checks(checks, correction_bytes):
    index = correction_codes(correction_bytes)
    result = []
    for row in checks:
        description = row['test_description']
        primary, subcategory, record, source = classify(description)
        fields = dict(test_code='', device='', primary_category=primary, subcategory=subcategory,
                      record_type=record, classification_source=source)
        match = re.fullmatch(r"Checking the (?:exit code|output) of the command '(.*)' on '([^']+)'", description, re.S)
        if match:
            command, device = match.groups()
            fields['device'] = device
            code = index.get((device, command))
            if code:
                fields.update(test_code=code, classification_source='correction_comment_exact')
                if code in CODE_CATEGORIES:
                    subcategory, record = CODE_CATEGORIES[code]
                    fields.update(primary_category='dns', subcategory=subcategory, record_type=record)
                else:
                    fields.update(primary_category='unclassified', subcategory='unknown', record_type=None)
        result.append({**row, **fields})
    return result
