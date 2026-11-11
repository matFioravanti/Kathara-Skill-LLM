#!/usr/bin/env python3
"""Verifica indipendente offline: lab.conf, .startup, IP, route /30 e /32, next-hop e loop."""
import csv, ipaddress, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'cost266.json').read_text())
map_rows=list(csv.DictReader((ROOT/'topology_mapping.csv').open()))
route_rows=list(csv.DictReader((ROOT/'routing_table.csv').open()))
conf=(ROOT/'lab.conf').read_text()
assert len(d['nodes'])==37 and len(d['edges'])==57
assert len(map_rows)==57
assert len(set(r['domain'] for r in map_rows))==57
assert len({r['subnet'] for r in map_rows})==57
assert all(int(r['edge_id'])==i and (int(r['source_id']),int(r['target_id']))==(e['source'],e['target']) for i,(r,e) in enumerate(zip(map_rows,d['edges'])))
entries={}
for line in conf.splitlines():
 m=re.fullmatch(r'([a-z0-9_]+)\[(\d+)\]="([a-z0-9_]+)"',line)
 if m:entries.setdefault(m.group(1),{})[int(m.group(2))]=m.group(3)
assert len(entries)==37 and len(set(entries))==37
for dev,es in entries.items():
 assert sorted(es)==list(range(len(es)))
 assert (ROOT/(dev+'.startup')).exists()
 sh=(ROOT/(dev+'.startup')).read_text()
 assert sh.count('ip -4 addr replace ')==len(es)+1
 assert sh.count('ip -4 route replace ')==57-len(es)+36
 assert 'net.ipv4.ip_forward=1' in sh
addresses=set()
for r in map_rows:
 for side in ['source','target']:
  dev=r[f'{side}_device'];eth=int(r[f'{side}_eth'][3:]);ip=r[f'{side}_ip']
  assert entries[dev][eth]==r['domain']
  assert ipaddress.ip_address(ip) in ipaddress.ip_network(r['subnet'])
  assert ip not in addresses;addresses.add(ip)
  sh=(ROOT/(dev+'.startup')).read_text()
  assert f'ip -4 addr replace {ip}/30 dev eth{eth}' in sh
assert len(addresses)==114
routers={n['id']: 'r_'+re.sub('[^a-z0-9]+','_',n['name'].lower()).strip('_') for n in d['nodes']}
for idx,dev in routers.items():
 ip=f'10.200.0.{idx+1}'
 assert ip not in addresses;addresses.add(ip)
 assert f'ip -4 addr replace {ip}/32 dev lo' in (ROOT/(dev+'.startup')).read_text()
assert len(addresses)==151
routes={dev:{} for dev in entries}
for r in route_rows:
 dev=r['source_device'];dest=r['destination'];nh=r['via'];eth=r['interface']
 assert dest not in routes[dev]
 routes[dev][dest]=r
 assert f'ip -4 route replace {dest} via {nh} dev {eth}' in (ROOT/(dev+'.startup')).read_text()
 # next hop belongs to point-to-point domain of the source router
 assert any(x[f'{side}_device']==dev and x[f'{side}_eth']==eth and x['target_ip' if side=='source' else 'source_ip']==nh for x in map_rows for side in ['source','target'])
assert len(route_rows)==sum(57-len(v)+36 for v in entries.values())
# Packet simulation according to the actual CSV forwarding entries.
addr_dest={}
for r in map_rows:
 addr_dest[r['source_ip']]=r['subnet'];addr_dest[r['target_ip']]=r['subnet']
for n,dev in routers.items():addr_dest[f'10.200.0.{n+1}']=f'10.200.0.{n+1}/32'
ns_to_devs={r['subnet']:{r['source_device'],r['target_device']} for r in map_rows}
loopdev={f'10.200.0.{n+1}/32':dev for n,dev in routers.items()}
lookup={}
for r in map_rows:
 for side in ['source','target']:
  dev=r[f'{side}_device'];ip=r['target_ip' if side=='source' else 'source_ip']
  lookup[(dev,r[f'{side}_eth'],ip)]=r[f'{"target" if side=="source" else "source"}_device']
count=0
for start in entries:
 for addr,dest_net in addr_dest.items():
  current=start;visited=set()
  while True:
   assert current not in visited, f'Routing loop: {start} -> {addr}'
   visited.add(current)
   if (dest_net in ns_to_devs and current in ns_to_devs[dest_net]) or (dest_net in loopdev and current==loopdev[dest_net]):break
   assert dest_net in routes[current],f'Missing route {current}->{dest_net}'
   entry=routes[current][dest_net]
   current=lookup[(current,entry['interface'],entry['via'])]
  count+=1
print(f'OK: {len(entries)} router, {len(map_rows)} link, {len(addresses)} IP unici, {len(route_rows)} rotte statiche, {count} simulazioni router->IP senza loop.')
print('Nota: verifica statica; avvio reale da verificare con Kathara + Docker.')
