"""Conservative classification of checker 0.1.14 reports; no external execution."""
import re
import yaml
from functools import lru_cache

RECORD_DESCRIPTION = 'Checking correctness of DNS records'
SUBCATEGORIES = ('devices', 'startup', 'topology', 'addressing', 'routing', 'forwarding',
                 'reachability', 'dns_service', 'dns_authority', 'dns_resolver',
                 'dns_record', 'dns_soa', 'dns_delegation', 'dns_recursion',
                 'dns_resolution', 'http', 'other_service', 'unknown')
PRIMARY = ('network', 'dns', 'applications', 'other', 'unclassified')


def _custom(command):
    if re.search(r'\b(?:ip\s+(?:-[46]\s+)?route|route\s+-[nN])\b', command):
        return 'network', 'routing', None
    if re.search(r'\b(?:net\.ipv[46]\.(?:ip_forward|conf\.all\.forwarding))\b', command):
        return 'network', 'forwarding', None
    query = re.search(r'\bdig\s+(?:@\S+\s+)?(?:\+\S+\s+)*\S+\s+(A|AAAA|MX|SOA|NS)\b', command, re.I)
    if query:
        kind = query.group(1).upper()
        if re.search(r'flags:.*\bra\b|recursion-check', command, re.I):
            return 'dns', 'dns_recursion', None
        if kind == 'SOA':
            return 'dns', 'dns_soa', kind
        if kind == 'NS' and '+norecurse' in command:
            return 'dns', 'dns_delegation', kind
        return 'dns', 'dns_resolution' if kind in ('A', 'AAAA') else 'dns_record', kind
    return 'unclassified', 'unknown', None


def classify(description):
    if description == RECORD_DESCRIPTION:
        return 'dns', 'dns_record', None, 'checker_description'
    if description.startswith(("Checking the exit code of the command '", "Checking the output of the command '")):
        command = description.split("command '", 1)[1].rsplit("' on '", 1)[0]
        return (*_custom(command), 'custom_command')
    rules = [
        (r'^Check existence of `[^`]+` file$', 'network', 'startup'),
        (r'^Check existence of `[^`]+`$', 'network', 'devices'),
        (r'^Checking the collision domain attached to (?:interface |`)', 'network', 'topology'),
        (r'^Checking the routing table of ', 'network', 'routing'),
        (r'^Checking (?:OSPF routes|OSPF neighbors|OSPF interface) on ', 'network', 'routing'),
        (r'^Check BGP routes for ', 'network', 'routing'),
        (r'^Checking that sysctl `net\.ipv[46]\.(?:ip_forward|conf\.all\.forwarding)` is set on ', 'network', 'forwarding'),
        (r'^Verifying the IP address ', 'network', 'addressing'),
        (r'^Verifying `.*` (?:not )?reachable from device ', 'network', 'reachability'),
        (r'^Checking .*\b(?:named) is (?:not )?running on device ', 'dns', 'dns_service'),
        (r'^Checking .*\b(?:ripd|ospfd|ospf6d|bgpd|zebra|watchfrr) is (?:not )?running on device ', 'network', 'routing'),
        (r'^Checking on `.*` that `.*` is the authority for domain ', 'dns', 'dns_authority'),
        (r'^Checking that `.*` is the local name server for device ', 'dns', 'dns_resolver'),
        (r'^HTTP [Cc]heck (?:on |\x27)', 'applications', 'http'),
    ]
    for pattern, primary, sub in rules:
        if re.search(pattern, description):
            return primary, sub, None, 'checker_description'
    return 'unclassified', 'unknown', None, 'unknown'


@lru_cache(maxsize=16)
def _expected_records(correction_bytes):
    dns = yaml.safe_load(correction_bytes)['test']['applications']['dns']
    clients = list(dict.fromkeys(client for values in dns['local_ns'].values() for client in values))
    return tuple((str(kind), str(name), str(client), addresses) for kind, names in dns['records'].items()
                 for name, addresses in names.items() for client in clients)


def classify_rows(rows, correction_path, version, complete, *, correction_bytes=None):
    classifications = [list(classify(row['test_description'])) for row in rows]
    positions = [i for i, row in enumerate(rows) if row['test_description'] == RECORD_DESCRIPTION]
    if not positions:
        return classifications
    expected = []
    try:
        if version != '0.1.14' or not complete:
            raise ValueError('unsupported version or incomplete report')
        raw = correction_bytes if correction_bytes is not None else correction_path.read_bytes()
        expected = _expected_records(raw)
        if len(expected) != len(positions) or positions != list(range(positions[0], positions[0] + len(positions))):
            raise ValueError('record count/order mismatch')
        for i, (kind, name, client, addresses) in zip(positions, expected):
            row = rows[i]
            if not row['passed']:
                prefix = f'{client} resolve {kind} {name} with IP '
                if not row['reason'].startswith(prefix) or not row['reason'].endswith(f' instead of {addresses}'):
                    raise ValueError('failure detail mismatch')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError):
        for i in positions:
            classifications[i][2:] = ['unknown', 'record_reconstruction_unknown']
        return classifications
    for i, (kind, _, _, _) in zip(positions, expected):
        classifications[i][2:] = [kind.upper(), 'correction_order_0.1.14']
    return classifications
