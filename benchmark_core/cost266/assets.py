"""Importazione verificata e bootstrap offline, separati dal compito DNS."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import csv
import io
import ipaddress
import json
import os
import re
import shlex
import shutil
import stat
import tempfile
import zipfile

import yaml

from ..correction_input import read_correction, validate_correction_lab
from ..workspace import copy_lab, tree_hash, write_json
from .protocol import clean_lab, digest, fingerprint, safe_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = PROJECT_ROOT/'experiments/cost266_data'
SOURCE_MANIFEST = 'source_manifest.json'
SOURCE_DIRECTORIES = ('source_backbone', 'source_dns')
SOURCE_GRAPH = 'source_backbone/cost266(1).json'
ARCHIVE_INPUTS = ('cost266.json', 'europa_cost266_static.zip', 'cost266_dns_multitld_v2.zip')


def resolve_inputs(inputs: Path | None = None) -> Path:
    """Argomento esplicito > COST266_INPUTS > sorgenti della checkout; mai la cwd."""
    location = inputs if inputs is not None else os.environ.get('COST266_INPUTS') or DEFAULT_INPUTS
    path = Path(location).expanduser()
    return safe_path(path if path.is_absolute() else PROJECT_ROOT/path)


def source_hashes(inputs: Path) -> dict[str, str]:
    """Hash dei soli sorgenti estratti, mai degli artefatti di preparazione."""
    result = {}
    for directory in SOURCE_DIRECTORIES:
        root = safe_path(inputs/directory)
        if not root.is_dir():
            raise ValueError(f'Asset mancanti: {directory}/')
        for path in sorted(root.rglob('*')):
            safe_path(path)
            if path.is_file():
                result[path.relative_to(inputs).as_posix()] = digest(path.read_bytes())
            elif not path.is_dir():
                raise ValueError(f'Sorgente non regolare: {path}')
    return result


def import_sources(inputs: Path, staging: Path) -> tuple[dict, dict]:
    """Riusa sorgenti con manifest oppure importa il pacchetto ZIP originale."""
    manifest_path = safe_path(inputs/SOURCE_MANIFEST)
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        expected = manifest.get('files')
        if manifest.get('schema') != 1 or not isinstance(expected, dict) or SOURCE_GRAPH not in expected:
            raise ValueError('Manifest sorgenti COST266 non valido')
        for name in expected:
            relative = PurePosixPath(name)
            if (not relative.parts or relative.is_absolute() or '..' in relative.parts or '\\' in name or
                    relative.parts[0] not in SOURCE_DIRECTORIES):
                raise ValueError(f'Percorso sorgente non sicuro: {name}')
        missing = [name for name in expected if not safe_path(inputs/name).is_file()]
        if missing:
            raise ValueError('Asset mancanti: '+', '.join(sorted(missing)))
        actual = source_hashes(inputs)
        changed = sorted(name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
        if changed:
            raise ValueError('Hash sorgenti non corrispondenti: '+', '.join(changed))
        for name in actual:
            target = staging/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(inputs/name, target)
        shutil.copy2(manifest_path, staging/SOURCE_MANIFEST)
        graph = json.loads((staging/SOURCE_GRAPH).read_text())
        assets = {SOURCE_MANIFEST: digest(manifest_path.read_bytes())}
    else:
        missing = [name for name in ARCHIVE_INPUTS if not safe_path(inputs/name).is_file()]
        if missing:
            raise ValueError('Asset mancanti: '+', '.join(missing)+
                             f'; in alternativa servono {SOURCE_MANIFEST}, source_backbone/ e source_dns/')
        extract(inputs/ARCHIVE_INPUTS[1], staging/'source_backbone')
        extract(inputs/ARCHIVE_INPUTS[2], staging/'source_dns')
        graph = json.loads((inputs/ARCHIVE_INPUTS[0]).read_text())
        assets = {name: digest((inputs/name).read_bytes()) for name in ARCHIVE_INPUTS}
    return graph, assets


def extract(archive: Path, target: Path):
    """Rifiuta traversal, link, duplicati e ZIP eccessivi prima di estrarre."""
    with zipfile.ZipFile(safe_path(archive)) as book:
        seen = set()
        if sum(i.file_size for i in book.infolist()) > 100_000_000:
            raise ValueError('Archivio troppo grande')
        for item in book.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or '..' in name.parts or '\\' in item.filename or
                    item.filename in seen or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError(f'Membro ZIP non sicuro: {item.filename}')
            seen.add(item.filename)
        book.extractall(target)


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))


def interfaces(lab: Path) -> dict[str, dict[int, str]]:
    result = defaultdict(dict)
    for device, number, domain in re.findall(r'(?m)^\s*([a-z0-9_]+)\[(\d+)\]\s*=\s*"?([A-Za-z0-9_-]+)"?\s*$',
                                            (lab / 'lab.conf').read_text()):
        if int(number) in result[device]:
            raise ValueError('Interfaccia duplicata')
        result[device][int(number)] = domain
    return dict(result)


def network_state(lab: Path):
    conf = interfaces(lab)
    addresses, routes = {}, {}
    owners = {}
    for device in conf:
        text = (lab / f'{device}.startup').read_text()
        addresses[device] = [(ipaddress.ip_interface(ip), dev) for ip, dev in
                             re.findall(r'(?m)^ip -4 addr replace (\S+) dev (\S+)', text)]
        routes[device] = [(ipaddress.ip_network(net), via, iface) for net, via, iface in
                          re.findall(r'(?m)^ip -4 route replace (\S+) via (\S+) dev (\S+)', text)]
        for ip, _ in addresses[device]:
            if str(ip.ip) in owners:
                raise ValueError(f'IP duplicato: {ip.ip}')
            owners[str(ip.ip)] = device
    return conf, addresses, routes, owners


def verify_routing(lab: Path, targets: list[str]) -> dict:
    """Simula forwarding IPv4 dalle route realmente presenti, senza Docker."""
    conf, addresses, routes, owners = network_state(lab)
    count = 0
    max_hops = 0
    for start in conf:
        for address in targets:
            dest = ipaddress.ip_address(address)
            current, seen = start, set()
            while True:
                if current in seen:
                    raise ValueError(f'Routing loop: {start} -> {address}')
                seen.add(current)
                if any(ip.ip == dest for ip, _ in addresses[current]):
                    break
                local = [(ip, dev) for ip, dev in addresses[current] if dest in ip.network and dev != 'lo']
                if local:
                    iface = local[0][1]
                    next_device = owners.get(address)
                    via = address
                else:
                    matches = [r for r in routes[current] if dest in r[0]]
                    if not matches:
                        raise ValueError(f'Rotta mancante {current} -> {address}')
                    _, via, iface = max(matches, key=lambda r: r[0].prefixlen)
                    next_device = owners.get(via)
                try:
                    domain = conf[current][int(iface.removeprefix('eth'))]
                except (KeyError, ValueError):
                    raise ValueError(f'Interfaccia non valida: {current}/{iface}') from None
                if not next_device or domain not in conf[next_device].values():
                    raise ValueError(f'Next-hop non adiacente: {current} via {via}')
                if not any(ipaddress.ip_address(via) in ip.network and dev == iface for ip, dev in addresses[current]):
                    raise ValueError('Next-hop fuori dalla rete connessa')
                if current != start and 'net.ipv4.ip_forward=1' not in (lab / f'{current}.startup').read_text():
                    raise ValueError(f'Forwarding disabilitato: {current}')
                current = next_device
            count += 1
            max_hops = max(max_hops, len(seen)-1)
    return {'simulated_paths': count, 'max_hops': max_hops, 'dynamic_validation': 'NOT_RUN'}


def validate_sources(backbone: Path, logical: Path, graph: dict) -> dict:
    if len(graph['nodes']) != 37 or len(graph['edges']) != 57:
        raise ValueError('COST266 deve contenere 37 nodi e 57 archi')
    if json.loads((backbone / 'cost266.json').read_text()) != graph:
        raise ValueError('JSON interno/esterno divergenti')
    nodes = {n['id']: 'r_' + re.sub('[^a-z0-9]+', '_', n['name'].lower()).strip('_') for n in graph['nodes']}
    if len(nodes) != 37 or len(set(nodes.values())) != 37:
        raise ValueError('Nodi duplicati')
    conf = interfaces(backbone)
    links = rows(backbone / 'topology_mapping.csv')
    if set(conf) != set(nodes.values()) or len(links) != 57:
        raise ValueError('Nomi router o collegamenti non corrispondono')
    domains = defaultdict(set)
    for dev, mapping in conf.items():
        if sorted(mapping) != list(range(len(mapping))):
            raise ValueError('Interfacce non contigue')
        for domain in mapping.values():
            domains[domain].add(dev)
    if len(domains) != 57 or any(len(v) != 2 for v in domains.values()):
        raise ValueError('Backbone non punto-punto')
    for edge, link in zip(graph['edges'], links):
        a, b = edge['source'], edge['target']
        if (int(link['source_id']), int(link['target_id'])) != (a, b) or domains[link['domain']] != {nodes[a], nodes[b]}:
            raise ValueError('Arco JSON non corrispondente')
        for side in ('source', 'target'):
            dev = link[side + '_device']; iface = link[side + '_eth']; ip = link[side + '_ip']
            if conf[dev][int(iface[3:])] != link['domain'] or f'ip -4 addr replace {ip}/30 dev {iface}' not in (backbone/f'{dev}.startup').read_text():
                raise ValueError('Indirizzi/link discordanti')
    zones = rows(logical / 'zone_inventory.csv')
    delegations = rows(logical / 'delegazioni.csv')
    cities = rows(logical / 'citta_domini_v2.csv')
    counts = Counter(z['tipo'] for z in zones)
    expected = {'root': 1, 'tld': 6, 'paese': 22, 'citta': 37, 'sottozona_citta': 111, 'funzionale': 24}
    # Il nome della categoria funzionale è verificato sul CSV, non desunto dalle immagini.
    functional = [k for k in counts if k not in ('root','tld','paese','citta','sottozona_citta')]
    if len(functional) == 1:
        expected[functional[0]] = expected.pop('funzionale')
    if counts != expected or len(zones) != 201 or len(delegations) != 200 or len(cities) != 37:
        raise ValueError(f'Inventario gerarchia inatteso: {dict(counts)}')
    by_name = {z['zona_fqdn']: z for z in zones}
    if len(by_name) != 201 or set(z['zona_fqdn'] for z in zones if z['tipo']=='tld') != {'europa.','infra.','research.','services.','lab.','test.'}:
        raise ValueError('Zone/TLD duplicati o inattesi')
    expected_edges = {(z['zona_genitore'], z['zona_fqdn']) for z in zones if z['zona_fqdn'] != '.'}
    if {(d['genitore'], d['zona_figlia']) for d in delegations} != expected_edges:
        raise ValueError('Deleghe discordanti')
    md = (logical / 'GERARCHIA_DNS_EUROPA_MULTITLD.md').read_text()
    tree = md.split('```text', 1)[1].split('```', 1)[0]
    tree_names = set(re.findall(r'(?:^|[\s─])([a-z0-9.-]*\.)\s+\[', tree))
    if tree_names != set(by_name):
        raise ValueError('Albero Markdown discordante dal CSV')
    for city in cities:
        node = int(city['cost266_id'])
        if nodes[node] != city['router_originale'] or city['zona_citta'] not in by_name:
            raise ValueError('Mapping città/router non corrispondente')
        if not all(city[k] in by_name for k in ('zona_services','zona_research','zona_admin')):
            raise ValueError('Sottozone cittadine discordanti')
    _, addresses, _, _ = network_state(backbone)
    routing = verify_routing(backbone, [str(ip.ip) for values in addresses.values() for ip, _ in values])
    return {'nodes': 37, 'edges': 57, 'zone_counts': dict(counts), 'zones': len(zones), 'delegations': len(delegations), **routing}


# Piano di deployment compatto esplicito: mai co-ospitare genitore e figlia.
ROLE_ROUTERS = {'root': 'r_amsterdam', 'tld_europa': 'r_amsterdam',
                'tld_infra': 'r_frankfurt', 'tld_research': 'r_frankfurt',
                'tld_services': 'r_rome', 'tld_lab': 'r_paris', 'tld_test': 'r_london',
                'countries': 'r_frankfurt', 'cities': 'r_rome', 'subzones': 'r_paris',
                'functional_1': 'r_london', 'functional_2': 'r_helsinki',
                'resolver_1': 'r_warsaw', 'resolver_2': 'r_zurich',
                'client_1': 'r_athens', 'client_2': 'r_lisbon'}


def bootstrap(backbone: Path, logical: Path, graph: dict, lab: Path) -> dict:
    # Copia soltanto dati di rete: strumenti, immagini e specifiche non entrano nell'AUT.
    lab.mkdir()
    shutil.copy2(backbone/'lab.conf', lab/'lab.conf')
    for startup in backbone.glob('*.startup'):
        shutil.copy2(startup, lab/startup.name)
    conf = interfaces(lab)
    router_ids = {'r_' + n['name'].lower(): n['id'] for n in graph['nodes']}
    roles, offsets = {}, Counter()
    attached = sorted(set(ROLE_ROUTERS.values()))
    for router in attached:
        idx = router_ids[router]
        subnet = f'10.210.{idx}.0/24'
        gateway = f'10.210.{idx}.1'
        iface = len(conf[router])
        with (lab/'lab.conf').open('a') as f:
            f.write(f'\n{router}[{iface}]="access_{idx:02d}"\n')
        with (lab/f'{router}.startup').open('a') as f:
            f.write(f'\n# Bootstrap COST266: rete accesso dichiarata {subnet}\nip -4 addr replace {gateway}/24 dev eth{iface}\n')
        for other in conf:
            if other == router:
                continue
            original = (backbone/f'{other}.startup').read_text()
            match = re.search(rf'(?m)^ip -4 route replace 10\.200\.0\.{idx+1}/32 via (\S+) dev (\S+)', original)
            if not match:
                raise ValueError(f'Rotta loopback mancante da {other} a {router}')
            with (lab/f'{other}.startup').open('a') as f:
                f.write(f'ip -4 route replace {subnet} via {match[1]} dev {match[2]}\n')
    for role, router in sorted(ROLE_ROUTERS.items()):
        idx = router_ids[router]; offsets[router] += 1
        address = f'10.210.{idx}.{9+offsets[router]}'
        device = 'c266_' + role
        roles[role] = {'device': device, 'role': role, 'router': router, 'address': address}
        with (lab/'lab.conf').open('a') as f:
            f.write(f'{device}[0]="access_{idx:02d}"\n{device}[image]="kathara/base"\n{device}[ipv6]="false"\n')
        (lab/f'{device}.startup').write_text('#!/bin/sh\nset -eu\n'
            f'ip -4 addr replace {address}/24 dev eth0\nip -4 route replace 0.0.0.0/0 via 10.210.{idx}.1 dev eth0\n'
            'systemctl stop named\n')
    zones = []
    for source in sorted(rows(logical/'zone_inventory.csv'), key=lambda z: (z['zona_fqdn'].count('.'), z['zona_fqdn'])):
        name, parent, kind = source['zona_fqdn'], source['zona_genitore'] or None, source['tipo']
        if kind == 'root': role, stage = 'root', 1
        elif kind == 'tld': role, stage = 'tld_' + name[:-1], 2
        elif kind == 'paese': role, stage = 'countries', 3
        elif kind == 'citta': role, stage = 'cities', 4
        elif kind == 'sottozona_citta': role, stage = 'subzones', 5
        else: role, stage = 'functional_' + str(name.count('.')-1), 5
        host = roles[role]
        ns = 'a.root-servers.' if name == '.' else 'ns1.' + name
        zone = {'name': name, 'parent': parent, 'kind': kind, 'stage': stage, 'device': host['device'],
                'address': host['address'], 'ns': ns, 'soa_contact': 'hostmaster.' + (name if name != '.' else 'root-servers.'), 'records': []}
        labels = []
        if kind == 'citta':
            labels = ['www', 'api', 'mail']
            zone['records'].append({'name': name, 'type': 'MX', 'value': '10 mail.'+name})
        elif kind == 'sottozona_citta':
            labels = {'services': ['portal','api'], 'research': ['git','data'], 'admin':['monitor','logs']}[name.split('.')[0]]
        # Alias DNS di servizio co-ospitati sull'host DNS reale; nessun server HTTP/SMTP richiesto.
        zone['records'] += [{'name': label+'.'+name, 'type':'A', 'value':host['address']} for label in labels]
        zones.append(zone)
    resolvers = [roles['resolver_1'], roles['resolver_2']]
    clients = [{**roles[f'client_{i}'], 'resolver': roles[f'resolver_{i}']['address']} for i in (1,2)]
    queries = [record for zone in zones for record in zone['records']]
    inventory = {'schema': 1, 'synthetic': False, 'roles': list(roles.values()), 'zones': zones,
                 'resolvers': resolvers, 'clients': clients, 'queries': queries,
                 'deployment': 'compact_v1: 16 host, più zone per ruolo, nessun genitore/figlio sullo stesso host; alias di servizio su host DNS',
                 'routing': verify_routing(lab, [r['address'] for r in roles.values()])}
    clean_lab(lab)
    return inventory


def dig_assert(server: str | None, name: str, record_type: str, expected: list[tuple], *, flags='') -> str:
    """Custom command compatibile col checker 0.1.14; nessuna eval shell dei dati."""
    query = ' '.join(shlex.quote(v) for v in ['dig', *(['@'+server] if server else []), name, record_type,
                                             '+time=2', '+tries=1', *flags.split()])
    conditions = []
    for index, fields in enumerate(expected):
        condition = ' && '.join(f'${column}=={json.dumps(value)}' for column, value in fields)
        conditions.append(f'({condition}) {{ok{index}=1}}')
    program = '\n'.join(conditions) + '\nEND {exit !(' + ' && '.join(f'ok{i}' for i in range(len(expected))) + ')}'
    script = f'out=$({query}) || exit 1\nprintf "%s\\n" "$out" | awk {shlex.quote(program)}'
    return 'sh -c ' + shlex.quote(script)


def correction(inventory: dict, lab: Path) -> tuple[dict, list[dict]]:
    custom, coverage = defaultdict(list), []
    probe = inventory['clients'][0]['device']
    zones = {z['name']: z for z in inventory['zones']}
    def add(device, command, kind, name):
        custom[device].append({'command': command, 'exit_code': 0})
        coverage.append({'device': device, 'command': command, 'kind': kind, 'name': name})
    for z in zones.values():
        add(probe, dig_assert(z['address'], z['name'], 'SOA', [((4,'SOA'),(5,z['ns']))], flags='+norecurse'), 'soa', z['name'])
        header = 'dig ' + shlex.quote('@'+z['address']) + ' ' + shlex.quote(z['name']) + ' SOA +time=2 +tries=1 +norecurse'
        add(probe, 'sh -c ' + shlex.quote(header + " | awk '/flags:/ && / aa[ ;]/ {ok=1} END {exit !ok}'"), 'authority', z['name'])
        add(probe, dig_assert(z['address'], z['name'], 'NS', [((1,z['name']),(4,'NS'),(5,z['ns']))], flags='+norecurse'), 'apex_ns', z['name'])
        add(probe, dig_assert(z['address'], z['ns'], 'A', [((1,z['ns']),(4,'A'),(5,z['address']))], flags='+norecurse'), 'ns_address', z['name'])
        if z['parent']:
            parent = zones[z['parent']]
            if parent['device'] == z['device']:
                raise ValueError('Oracle referral richiede server parent/child distinti')
            add(probe, dig_assert(parent['address'], '__delegation_probe.'+z['name'], 'A',
                [((1,z['name']),(4,'NS'),(5,z['ns'])), ((1,z['ns']),(4,'A'),(5,z['address']))], flags='+norecurse'), 'delegation_glue', z['name'])
        for record in z['records']:
            value = record['value'].split()
            expected = ((1,record['name']),(4,record['type']), *tuple((5+i,v) for i,v in enumerate(value)))
            add(probe, dig_assert(z['address'], record['name'], record['type'], [expected], flags='+norecurse'), 'record', record['name'])
    for client in inventory['clients']:
        add(client['device'], 'cat /etc/resolv.conf', 'client_resolver', client['device'])
        # Check resolver address via supported regex/output instead of an assumed checker category.
        custom[client['device']][-1] = {'command': 'cat /etc/resolv.conf', 'regex_match': r'(?m)^nameserver\s+'+re.escape(client['resolver'])+r'\s*$'}
        for record in inventory['queries']:
            value = record['value'].split()
            expected = ((1,record['name']),(4,record['type']), *tuple((5+i,v) for i,v in enumerate(value)))
            add(client['device'], dig_assert(None, record['name'], record['type'], [expected]), 'client_resolution', record['name'])
    return {'lab_inline': (lab/'lab.conf').read_text(), 'convergence_time': 60, 'default_image':'kathara/base',
            'test': {'requiring_startup': sorted(interfaces(lab)),
                     'applications': {'dns': {'authoritative': {z['name']: [z['address']] for z in zones.values()},
                                              'local_ns': {r['address']: [c['device'] for c in inventory['clients'] if c['resolver']==r['address']] for r in inventory['resolvers']}}},
                     'custom_commands': dict(custom)}}, coverage


def prepare(inputs: Path | None, destination: Path) -> dict:
    inputs = resolve_inputs(inputs)
    destination = safe_path(destination)
    if destination.exists():
        raise ValueError(f'Dataset preesistente preservato: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cost266-import-', dir=destination.parent) as temp:
        staging = Path(temp)
        graph, asset_hashes = import_sources(inputs, staging)
        backbone = staging/'source_backbone/europa_cost266_static'
        validation = validate_sources(backbone, staging/'source_dns', graph)
        inventory = bootstrap(backbone, staging/'source_dns', graph, staging/'lab')
        oracle, coverage = correction(inventory, staging/'lab')
        (staging/'correction.yaml').write_text(yaml.safe_dump(oracle, sort_keys=False, allow_unicode=True, width=120))
        _, oracle_hash = read_correction(staging/'correction.yaml')
        validate_correction_lab(staging/'correction.yaml', staging/'lab')
        write_json(staging/'inventory.json', inventory)
        write_json(staging/'oracle_coverage.json', {'checks': coverage, 'runtime_verified': False,
            'limitations': ['Comandi custom validati sullo schema installato e con fixture; BIND/dig reali da verificare.',
                            'Nessun test di semantica NXDOMAIN/DNSSEC: test. è una zona tematica.']})
        report = {'schema':1, 'assets':asset_hashes, 'source_files':source_hashes(staging), 'validation':validation,
                  'baseline_sha256':tree_hash(staging/'lab'), 'inventory_sha256':digest((staging/'inventory.json').read_bytes()),
                  'correction_sha256':oracle_hash, 'status':'STATICALLY_PREPARED_DYNAMIC_NOT_RUN'}
        write_json(staging/'preparation.json', report)
        # rename atomico del solo dataset nuovo, mai degli scenari lab_01..03.
        staging.rename(destination)
    return report


def load_dataset(path: Path) -> tuple[dict, dict]:
    safe_path(path)
    for name in ('inventory.json','preparation.json','correction.yaml'):
        safe_path(path/name)
    inventory = json.loads((path/'inventory.json').read_text())
    report = json.loads((path/'preparation.json').read_text())
    clean_lab(path/'lab')
    for actual, expected in ((tree_hash(path/'lab'), report['baseline_sha256']),
                             (digest((path/'inventory.json').read_bytes()), report['inventory_sha256']),
                             (read_correction(path/'correction.yaml')[1], report['correction_sha256'])):
        if actual != expected:
            raise ValueError('Hash dataset non corrispondente: importare in un nuovo percorso')
    validate_correction_lab(path/'correction.yaml', path/'lab')
    if inventory.get('schema') != 1 or inventory.get('synthetic') is not False:
        raise ValueError('Dataset operativo mancante o sintetico')
    for zone in inventory['zones']:
        device, address = zone['device'], zone['address']
        text = (path/'lab'/f'{device}.startup').read_text()
        if f'ip -4 addr replace {address}/24 dev eth0' not in text:
            raise ValueError('Binding inventario assente dalla baseline')
    return inventory, report
