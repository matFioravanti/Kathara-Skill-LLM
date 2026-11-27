"""Offline definitions and exact matching for canonical and custom DNS corrections."""
import hashlib
import json
import re
from collections import defaultdict

import yaml

from .check_classification import classify
from .v3_classification import CODE_CATEGORIES


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class CorrectionCatalog:
    def __init__(self, content):
        self.sha256 = hashlib.sha256(content).hexdigest()
        text = content.decode('utf-8')
        self.lines = text.splitlines()
        self.data = yaml.safe_load(text)
        self.nodes = {}
        self.definitions = []
        self.by_description = defaultdict(list)
        self.headers = {}
        for i, line in enumerate(self.lines):
            match = re.search(r'#\s*---\s*(CS\d+)\s*[—–-]\s*(.*?)\s*---', line)
            if match:
                comment = [line.strip()]
                j = i + 1
                while j < len(self.lines) and self.lines[j].strip().startswith('#'):
                    comment.append(self.lines[j].strip())
                    j += 1
                self.headers[match.group(1)] = (i + 1, match.group(2), '\n'.join(comment))

        def visit(node, path=()):
            self.nodes[path] = node
            if isinstance(node, yaml.MappingNode):
                for k, v in node.value:
                    visit(v, (*path, str(k.value)))
            elif isinstance(node, yaml.SequenceNode):
                for i, v in enumerate(node.value):
                    visit(v, (*path, str(i)))
        visit(yaml.compose(text))
        self.build()

    def line(self, path):
        node = self.nodes.get(tuple(map(str, path)))
        return node.start_mark.line + 1 if node else None

    def add(self, description, device, path, code=None, expected=None, command='', record_type='', comment='', meaning=''):
        header = self.headers.get(code)
        if header and not comment:
            comment, meaning = header[2], header[1]
        category, sub, rec, _ = classify(description)
        if code in CODE_CATEGORIES:
            category = 'dns'
            sub, rec = CODE_CATEGORIES[code]
        line = self.line(path)
        item = dict(test_description=description, device=device, definition_path='.'.join(map(str, path)),
                    correction_line=line, error_code=code if (header or comment) else 'UNCLASSIFIED',
                    error_description=meaning or comment, correction_comment=comment, check_category=category,
                    check_subcategory=sub, check_type='custom_command' if command.startswith('sh -c') else sub,
                    record_type=record_type or rec or '', expected_result=json.dumps(expected, ensure_ascii=False),
                    command=command)
        if description == 'Checking correctness of DNS records':
            item.update(check_category='dns', check_subcategory='dns_record', check_type='dns_record')
        item['definition_id'] = digest(json.dumps(item, sort_keys=True, ensure_ascii=False))
        item['common_control_id'] = digest(json.dumps({k: item[k] for k in
            ('test_description', 'device', 'expected_result', 'command', 'record_type')}, sort_keys=True))
        self.definitions.append(item)
        self.by_description[description].append(item)

    def build(self):
        t = self.data.get('test', {})
        inline = self.data.get('lab_inline', '')
        interfaces = re.findall(r'^\s*([A-Za-z0-9_-]+)\[(\d+)\]\s*=\s*[\"\x27]([^\"\x27]+)[\"\x27]', inline, re.M)
        devices = list(dict.fromkeys(d for d, _, _ in interfaces))
        for device in devices:
            self.add(f'Check existence of `{device}`', device, ('lab_inline',), 'CS01', True)
        for device, number, link in interfaces:
            self.add(f'Checking the collision domain attached to interface `eth{number}` of `{device}`',
                     device, ('lab_inline',), 'CS02', {'interface': 'eth' + number, 'collision_domain': link})
        for i, device in enumerate(t.get('requiring_startup', [])):
            self.add(f'Check existence of `{device}.startup` file', device, ('test', 'requiring_startup', i), 'CS03', True)
        ip_devices = {}
        for device, addresses in t.get('ip_mapping', {}).items():
            for iface, ip in addresses.items():
                ip_devices[str(ip).split('/')[0]] = device
                self.add(f'Verifying the IP address ({ip}) assigned to eth{iface} of {device}', device,
                         ('test', 'ip_mapping', device, iface), 'CS04', ip, command=f'ip -j address show dev eth{iface}')
        for device, daemons in t.get('daemons', {}).items():
            for i, daemon in enumerate(daemons):
                neg = daemon.startswith('!')
                self.add(f'Checking that {daemon.lstrip("!")} is {"not " if neg else ""}running on device `{device}`',
                         device, ('test', 'daemons', device, i), 'CS05', not neg, command=f'pgrep {daemon.lstrip("!")}')
        for device, routes in t.get('kernel_routes', {}).items():
            self.add(f'Checking the routing table of {device}', device, ('test', 'kernel_routes', device), 'CS06', routes, command='ip -j route')
        for device, destinations in t.get('reachability', {}).items():
            for i, dest in enumerate(destinations):
                neg = dest.startswith('!')
                self.add(f'Verifying `{dest.lstrip("!")}` {"not " if neg else ""}reachable from device `{device}`', device,
                         ('test', 'reachability', device, i), 'CS07', not neg, command=f"bash -c 'ping -q -n -c 1 {dest.lstrip('!')}'")
        dns = t.get('applications', {}).get('dns', {})
        for domain, servers in dns.get('authoritative', {}).items():
            for i, server in enumerate(servers):
                targets = [server]
                if domain == '.':
                    targets += list(servers) + list(dns.get('local_ns', {}))
                for target in targets:
                    device = ip_devices.get(target, '')
                    self.add(f'Checking on `{device}` that `{server}` is the authority for domain `{domain}`', device,
                             ('test', 'applications', 'dns', 'authoritative', domain, i), 'CS08', server,
                             command=f'dig NS {domain} @{target}', record_type='NS')
        clients = []
        for server, machines in dns.get('local_ns', {}).items():
            for i, device in enumerate(machines):
                if device not in clients:
                    clients.append(device)
                self.add(f'Checking that `{server}` is the local name server for device `{device}`', device,
                         ('test', 'applications', 'dns', 'local_ns', server, i), 'CS09', server, command='cat /etc/resolv.conf')
        for kind, records in dns.get('records', {}).items():
            for name, expected in records.items():
                for device in clients:
                    code = {'A': 'CS10', 'MX': 'CS11'}.get(kind)
                    self.add('Checking correctness of DNS records', device,
                             ('test', 'applications', 'dns', 'records', kind, name), code, expected,
                             command=f'dig +short {kind} {name}', record_type=kind)
        for device, commands in t.get('custom_commands', {}).items():
            for i, entry in enumerate(commands):
                path = ('test', 'custom_commands', device, i)
                n = self.line(path) - 2
                while n >= 0 and not self.lines[n].strip():
                    n -= 1
                comment = self.lines[n].strip() if n >= 0 else ''
                match = re.fullmatch(r'#\s*(DNS_[A-Z0-9_]+)\s+-\s+(.+)', comment)
                for field, phrase in (('exit_code', 'exit code'), ('output', 'output'), ('regex_match', 'output')):
                    if field in entry:
                        self.add(f"Checking the {phrase} of the command '{entry['command']}' on '{device}'", device,
                                 (*path, field), match.group(1) if match else None, entry[field], entry['command'],
                                 comment=comment if match else '', meaning=match.group(2) if match else '')

    def match(self, description, reason):
        candidates = self.by_description.get(description, [])
        if description == 'Checking correctness of DNS records':
            m = re.fullmatch(r'(\S+) resolve (\S+) (\S+) with IP (.*?) instead of (.*)', reason, re.S)
            if not m:
                return None, 'DNS_RECORD_IDENTIFIERS_ABSENT: il CSV non indica client, nome o tipo; ordine non usato'
            device, kind, name, _, expected = m.groups()
            try:
                import ast
                expected = ast.literal_eval(expected)
            except (ValueError, SyntaxError):
                return None, 'DNS_RECORD_EXPECTED_UNREADABLE'
            candidates = [c for c in candidates if c['device'] == device and c['command'] == f'dig +short {kind} {name}'
                          and json.loads(c['expected_result']) == expected]
        if not candidates:
            return None, 'NO_EXACT_DEFINITION: nessuna corrispondenza certa nello snapshot'
        signatures = {json.dumps({k: v for k, v in c.items() if k != 'definition_id'}, sort_keys=True) for c in candidates}
        if len(signatures) != 1:
            return None, 'AMBIGUOUS_DEFINITION: più definizioni compatibili'
        result = candidates[0]
        return result, '' if result['error_code'] != 'UNCLASSIFIED' else 'NO_CODE_IN_CORRECTION: definizione identificata, codice assente'
