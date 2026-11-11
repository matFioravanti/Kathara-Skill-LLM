#!/usr/bin/env python3
"""Genera il laboratorio Kathara COST266 IPv4 statico dal JSON TopoHub/SNDlib.
Solo libreria standard per la generazione; matplotlib opzionale per la mappa.
"""
import csv
import heapq
import ipaddress
import json
import re
import shutil
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'cost266(1).json'
OUT = BASE / 'europa_cost266_static'
WAN_SUPERNET = ipaddress.IPv4Network('10.100.0.0/24')
LOOPBASE = ipaddress.IPv4Network('10.200.0.0/24')

def devname(s):
    ascii_name = unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode()
    return 'r_'+re.sub(r'[^a-z0-9]+','_',ascii_name.lower()).strip('_')

def save(path, text):
    path.write_text(text, encoding='utf-8', newline='\n')

def shortest_paths(src, graph):
    """Dijkstra su lunghezze intere centi-unità, tie-break lessicografico stabile."""
    known = {src: (0, (src,))}
    pq = [(0, (src,), src)]
    while pq:
        d, path, u = heapq.heappop(pq)
        if known[u] != (d,path):
            continue
        for v, w in graph[u]:
            cand = (d+w, path+(v,))
            if v not in known or cand < known[v]:
                known[v] = cand
                heapq.heappush(pq, (cand[0],cand[1],v))
    return known

def main():
    raw = json.loads(SOURCE.read_text(encoding='utf-8'))
    nodes = sorted(raw['nodes'],key=lambda n:n['id'])
    edges = raw['edges']
    assert len(nodes)==37 and len(edges)==57
    ids = {n['id'] for n in nodes}
    assert ids == set(range(37))
    names = {n['id']: devname(n['name']) for n in nodes}
    assert len(set(names.values())) == len(nodes)
    seen=set()
    graph={i:[] for i in ids}
    for e in edges:
        u,v=e['source'],e['target']
        assert u in ids and v in ids and u!=v
        key=tuple(sorted((u,v)))
        assert key not in seen;seen.add(key)
        d=int(round(float(e['dist'])*100))
        graph[u].append((v,d));graph[v].append((u,d))
    assert len(shortest_paths(0,graph))==37, 'Graph not connected'
    for n in graph:
        graph[n].sort()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    iface={u:[] for u in ids}
    mapping=[]
    wan_nets=list(WAN_SUPERNET.subnets(new_prefix=30))
    for idx,e in enumerate(edges):
        u,v=e['source'],e['target']
        net=wan_nets[idx]
        prefix=str(net)
        u_if=len(iface[u]);v_if=len(iface[v]);
        u_ip=str(net.network_address+1)
        v_ip=str(net.network_address+2)
        domain=f'wan_{min(u,v):02d}_{max(u,v):02d}'
        eobj={
            'edge_id':idx,'source_id':u,'source_city':nodes[u]['name'],'source_device':names[u],
            'source_eth':f'eth{u_if}','source_ip':u_ip,
            'target_id':v,'target_city':nodes[v]['name'],'target_device':names[v],
            'target_eth':f'eth{v_if}','target_ip':v_ip,
            'subnet':prefix,'domain':domain,'dist':float(e['dist'])
        }
        mapping.append(eobj)
        iface[u].append({'idx':u_if,'neighbor':v,'ip':u_ip,'peer_ip':v_ip,'network':prefix,'domain':domain})
        iface[v].append({'idx':v_if,'neighbor':u,'ip':v_ip,'peer_ip':u_ip,'network':prefix,'domain':domain})
    assert len({e['domain'] for e in mapping})==57
    assert all(2<=len(iface[i])<=5 for i in ids)
    assert sum(len(v) for v in iface.values())==2*57
    all_shortest={i:shortest_paths(i,graph) for i in ids}
    loopback={i: f'10.200.0.{i+1}' for i in ids}
    routes_by_dev={i:{} for i in ids}
    route_rows=[]
    paths_rows=[]
    for src in sorted(ids):
        adjacent={ipaddress.IPv4Network(lnk['network']) for lnk in iface[src]}
        # Ogni /30 non locale: instradamento verso l'estremità con distanza pesata minima.
        for e in mapping:
            net=ipaddress.IPv4Network(e['subnet'])
            if net in adjacent:
                continue
            u,v=e['source_id'],e['target_id']
            candidates=[(*all_shortest[src][endpoint],endpoint) for endpoint in [u,v]]
            d,path,endpoint=min(candidates)
            nexthop=path[1]
            link=next(a for a in iface[src] if a['neighbor']==nexthop)
            route={'destination':str(net),'via':link['peer_ip'],'dev':f"eth{link['idx']}",
                   'next_router':nexthop,'distance_centi':d,'endpoint':endpoint}
            routes_by_dev[src][str(net)]=route
            route_rows.append({'source_device':names[src],'destination':str(net),
                'via':route['via'],'interface':route['dev'],'next_router':names[nexthop],
                'route_type':'wan','distance':d/100})
        for dst in sorted(ids):
            d,path=all_shortest[src][dst]
            paths_rows.append({'source':names[src],'destination':names[dst],
              'destination_loopback':loopback[dst], 'distance':d/100,
              'hops':len(path)-1,'path':' > '.join(names[r] for r in path)})
            if src==dst:continue
            nexthop=path[1]
            link=next(a for a in iface[src] if a['neighbor']==nexthop)
            net=f'{loopback[dst]}/32'
            route={'destination':net,'via':link['peer_ip'],'dev':f"eth{link['idx']}",
                   'next_router':nexthop,'distance_centi':d,'endpoint':dst}
            routes_by_dev[src][net]=route
            route_rows.append({'source_device':names[src],'destination':net,
                'via':route['via'],'interface':route['dev'],'next_router':names[nexthop],
                'route_type':'loopback','distance':d/100})
    # Costruisci lab.conf in sintassi riconosciuta da Kathara.
    lines=[
        '# COST266 - rete europea originale: 37 router, 57 collegamenti.',
        '# Nessun router o collegamento aggiuntivo: edge => dominio punto-punto.',
        'LAB_NAME="europa_cost266_static"',
        'LAB_DESCRIPTION="COST266 European backbone - static IPv4 weighted shortest paths"',
        'LAB_VERSION="1.0"',
        '',
    ]
    for n in nodes:
        u=n['id'];dev=names[u]
        lines.extend([f'# {n["name"]} (COST266 node {u}), {len(iface[u])} link(s)',
                      f'{dev}[image]="kathara/core"',
                      f'{dev}[ipv6]="false"'])
        for lnk in iface[u]:
            lines.append(f'{dev}[{lnk["idx"]}]="{lnk["domain"]}"')
        lines.append('')
        commands=[
            '#!/bin/sh',
            f'# COST266 node {u}: {n["name"]} ({dev})',
            '# IP link 10.100.0.0/24 suddiviso in /30; loopback 10.200.0.0/24.',
            '# Script rigenerato deterministicamente dal JSON COST266.',
            'set -eu',
            'sysctl -w net.ipv4.ip_forward=1 >/dev/null',
            'sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null',
            'sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null',
            f'ip -4 addr replace {loopback[u]}/32 dev lo',
        ]
        for lnk in iface[u]:
            commands.append(f'ip -4 addr replace {lnk["ip"]}/30 dev eth{lnk["idx"]} # link to {names[lnk["neighbor"]]}')
        commands.extend(['', '# Routing statico per ogni rete WAN remota e per le loopback remote.'])
        for net,route in sorted(routes_by_dev[u].items(), key=lambda it:(ipaddress.IPv4Network(it[0]).network_address, -ipaddress.IPv4Network(it[0]).prefixlen)):
            commands.append(f'ip -4 route replace {net} via {route["via"]} dev {route["dev"]}')
        commands.append('')
        save(OUT/(dev+'.startup'),'\n'.join(commands))
    save(OUT/'lab.conf','\n'.join(lines))
    def write_csv(name,rows):
        with (OUT/name).open('w',newline='',encoding='utf-8') as fp:
            writer=csv.DictWriter(fp,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_csv('topology_mapping.csv',mapping)
    write_csv('routing_table.csv',route_rows)
    write_csv('shortest_paths.csv',paths_rows)
    (OUT/'cost266.json').write_text(SOURCE.read_text(encoding='utf-8'), encoding='utf-8')
    # Verifica simulata della disponibilita' dell'instradamento per tutti i router verso ogni IP.
    addr_to_net={}
    for row in mapping:
        for key in ['source_ip','target_ip']:
            addr_to_net[row[key]]=row['subnet']
    for u in ids:
        addr_to_net[loopback[u]]=f'{loopback[u]}/32'
    hops=[]
    for src in sorted(ids):
        for dest,net in addr_to_net.items():
            cur=src;visited={cur};steps=0
            while True:
                if net.endswith('/32') and loopback[cur]==dest:
                    break
                if net.endswith('/30') and any(lnk['network']==net for lnk in iface[cur]):
                    break
                assert net in routes_by_dev[cur], f'Missing route: {names[cur]} -> {net}'
                route=routes_by_dev[cur][net]
                link=next(lnk for lnk in iface[cur] if route['dev']==f"eth{lnk['idx']}")
                assert link['neighbor']==route['next_router'] and link['peer_ip']==route['via']
                cur=route['next_router'];steps+=1
                assert cur not in visited, f'Loop {names[src]} destination {dest}'
                assert steps<37
                visited.add(cur)
            hops.append(steps)
    all_ips=list(addr_to_net)
    assert len(all_ips)==151, f'Expected 114 link IPs + 37 loopback IPs, got {len(all_ips)}'
    assert len(route_rows)==sum(57-len(iface[u])+36 for u in ids)
    assert len(paths_rows)==37*37
    # Validazione della sintassi per startup: ogni interfaccia e' referenziata una volta.
    for u in ids:
        sh=(OUT/(names[u]+'.startup')).read_text()
        assert sh.count('addr replace ')==len(iface[u])+1
        assert sh.count('route replace ')==57-len(iface[u])+36
        assert all(f'{names[u]}[{i}]=' in (OUT/'lab.conf').read_text() for i in range(len(iface[u])))
    # Specifica prompt operativa che la SkillCreazione chiede di redigere.
    spec=f'''# Specifica strutturata - Kathara SkillCreazione\n\n- **Directory:** `europa_cost266_static/`\n- **Nome:** `europa_cost266_static`\n- **Sorgente dati:** `cost266.json` (COST266/TopoHub).\n- **Topologia:** 37 router con nomi `r_<city>` e 57 domini di collisione distinti, uno per ciascun link originale. Nessuna nuova interconnessione.\n- **Indirizzamento:** IPv4 statico: 57 sottoreti /30 successive di `10.100.0.0/24`; indirizzo .1 lato source e .2 lato target in ordine del JSON. Loopback /32 `10.200.0.(id+1)`.\n- **Routing:** completamente statico. Cammini minimi Dijkstra pesati con campo `dist`; rotta /32 per ogni altra loopback; rotta /30 per ogni link non direttamente connesso, scelta verso l'estremita' piu' vicina. In caso di pari costo, spareggio per path di ID lessicograficamente minore.\n- **Immagine:** `kathara/core`; nessun demone di routing. IPv6 disabilitato.\n- **File richiesti:** `lab.conf`, 37 `<router>.startup`, `README.md`, CSV di collegamenti e rotte, JSON originale, strumenti di verifica.\n- **Verifica progettata:** corrispondenza dei nodi e link, unicita' degli IP e domini, route-next-hop adiacenti, nessun loop su ciascuna delle 37*151 = {len(hops)} coppie router/IP, prova dinamica esterna con Kathara.\n- **Assunzioni:** topologia BASE senza host DNS; la fase DNS e' una variante successiva con host e link di accesso da aggiungere prima dell'applicazione della skill DNS. `demands` ed `ecmp_*` non sono convertiti in link o router.\n'''
    save(OUT/'SPECIFICA.md',spec)
    readme=f'''# Laboratorio Kathara - COST266 Europa, routing statico\n\nTopologia europea ricostruita fedelmente dal file `cost266.json` usando **37 router** e **57 collegamenti**.\nOgni città e' un router (`r_rome`, `r_paris`, ecc.); ogni edge e' un dominio di collisione\npunto-punto distinto. Nessun router, switch o collegamento di backbone e' stato inventato.\n\n## Piano IP\n\n- WAN: `10.100.0.0/24`, suddivisa in **57 sottoreti /30**, una per ogni edge nell'ordine del JSON.\n- Ogni router ha una loopback `/32` `10.200.0.(id+1)` per ping, traceroute e benchmark.\n- Non ci sono indirizzi duplicati e ogni router ha `net.ipv4.ip_forward=1`.\n- IPv6 disabilitato.\n- Routing STATICO completo, con pesi Dijkstra = `dist` del JSON; nessun OSPF/BGP/RIP.\n\nVedi `topology_mapping.csv` per collegamenti / interface / IP; `routing_table.csv` per tutte\nle rotte, `shortest_paths.csv` per i 1.369 percorsi tra coppie di città.\n\n## Requisiti\n\nKathara e Docker installati e avviati; risorse sufficienti a eseguire contemporaneamente\n37 container. L'immagine usata per i router e' `kathara/core`.\n\n## Avvio sul tuo computer\n\n```bash\ncd europa_cost266_static\npython3 verify_lab.py           # verifica statica senza Docker\nkathara check                  # ambiente Kathara e Docker\nkathara lstart --print         # controllo preliminare di lab.conf (nessun avvio)\nkathara lstart --noterminals   # avvio dei 37 router\nkathara linfo                  # lista router attivi\n```\n\n## Esempi di test dinamici\n\nRoma: COST266 id=28, loopback `10.200.0.29`. Amsterdam: id=0, loopback `10.200.0.1`.\n\n```bash\nkathara exec r_rome -- ip -4 addr show\nkathara exec r_rome -- ip -4 route show\nkathara exec r_rome -- ping -c 3 10.200.0.1\nkathara exec r_amsterdam -- ping -c 3 10.200.0.29\nkathara exec r_rome -- traceroute -n 10.200.0.1\nkathara lclean\n```\n\nPer verificare l'intera matrice di ping inter-router (1.332 test), puoi usare\n`python3 runtime_ping.py` dal computer host **dopo** l'avvio del laboratorio.\n\n## Uso per la tesi DNS\n\nQuesto ZIP rappresenta il backbone base di routing statico. **Non include\nserver BIND, resolver o client DNS**: per creare gli scenari DNS occorre\nprima aggiungere host e LAN d'accesso in una variante del laboratorio; successivamente\nla skill `kathara-dns` puo' configurare tali host preservando indirizzi, rotte e link.\nI dati `demands` e `ecmp_*` originali rimangono nel JSON per eventuali analisi,\nma non sono configurazioni di rete immediatamente eseguibili.\n\n## Verifica\n\nIl generatore ha controllato staticamente {len(hops)} percorsi router→IP (114 indirizzi\nWAN e 37 loopback), inclusa assenza di loop di next-hop. Ciò NON sostituisce\nuna prova effettiva con `kathara lstart`: la verifica dinamica richiede Kathara\ne Docker sul tuo computer.\n\nLa sintassi `lab.conf` segue la SkillCreazione e la [documentazione ufficiale](https://www.kathara.org/man-pages/kathara-lab.conf.5.html).\n'''
    save(OUT/'README.md',readme)
    runtime_ping='''#!/usr/bin/env python3\n"""Ping dinamico di tutte le 37*36 coppie di router Kathara (richiede un lab avviato)."""\nimport concurrent.futures, csv, json, subprocess, sys, time\nfrom pathlib import Path\n\nlab=Path(__file__).resolve().parent\ndata=json.loads((lab/'cost266.json').read_text())\nitems=sorted(data['nodes'],key=lambda n:n['id'])\ndef name(s):\n import re,unicodedata\n s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()\n return 'r_'+re.sub('[^a-z0-9]+','_',s).strip('_')\npairs=[(a,b) for a in items for b in items if a['id']!=b['id']]\ndef check(pair):\n a,b=pair\n dest=f'10.200.0.{b["id"]+1}'\n proc=subprocess.run(['kathara','exec',name(a['name']),'--','ping','-c','1','-W','2',dest],capture_output=True,text=True,timeout=25)\n return (a['id'],b['id'],name(a['name']),name(b['name']),dest,proc.returncode==0)\nprint(f'Verifico {len(pairs)} ping (tempo dipendente dalla macchina).',flush=True)\nresults=[]\nwith concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:\n for index,row in enumerate(pool.map(check,pairs),start=1):\n  results.append(row)\n  if index%100==0:print(f'{index}/{len(pairs)}',flush=True)\nout=lab/'runtime_ping_results.csv'\nwith out.open('w',newline='') as f:\n w=csv.writer(f);w.writerow(['source_id','dest_id','source','destination','ip','success']);w.writerows(results)\nok=sum(r[-1] for r in results)\nprint(f'Ping riusciti: {ok}/{len(results)}. File: {out}')\nsys.exit(0 if ok==len(results) else 1)\n'''
    save(OUT/'runtime_ping.py',runtime_ping)
    verify='''#!/usr/bin/env python3\n"""Verifica indipendente offline: lab.conf, .startup, IP, route /30 e /32, next-hop e loop."""\nimport csv, ipaddress, json, re\nfrom pathlib import Path\nROOT=Path(__file__).resolve().parent\nd=json.loads((ROOT/'cost266.json').read_text())\nmap_rows=list(csv.DictReader((ROOT/'topology_mapping.csv').open()))\nroute_rows=list(csv.DictReader((ROOT/'routing_table.csv').open()))\nconf=(ROOT/'lab.conf').read_text()\nassert len(d['nodes'])==37 and len(d['edges'])==57\nassert len(map_rows)==57\nassert len(set(r['domain'] for r in map_rows))==57\nassert len({r['subnet'] for r in map_rows})==57\nassert all(int(r['edge_id'])==i and (int(r['source_id']),int(r['target_id']))==(e['source'],e['target']) for i,(r,e) in enumerate(zip(map_rows,d['edges'])))\nentries={}\nfor line in conf.splitlines():\n m=re.fullmatch(r'([a-z0-9_]+)\\[(\\d+)\\]="([a-z0-9_]+)"',line)\n if m:entries.setdefault(m.group(1),{})[int(m.group(2))]=m.group(3)\nassert len(entries)==37 and len(set(entries))==37\nfor dev,es in entries.items():\n assert sorted(es)==list(range(len(es)))\n assert (ROOT/(dev+'.startup')).exists()\n sh=(ROOT/(dev+'.startup')).read_text()\n assert sh.count('ip -4 addr replace ')==len(es)+1\n assert sh.count('ip -4 route replace ')==57-len(es)+36\n assert 'net.ipv4.ip_forward=1' in sh\naddresses=set()\nfor r in map_rows:\n for side in ['source','target']:\n  dev=r[f'{side}_device'];eth=int(r[f'{side}_eth'][3:]);ip=r[f'{side}_ip']\n  assert entries[dev][eth]==r['domain']\n  assert ipaddress.ip_address(ip) in ipaddress.ip_network(r['subnet'])\n  assert ip not in addresses;addresses.add(ip)\n  sh=(ROOT/(dev+'.startup')).read_text()\n  assert f'ip -4 addr replace {ip}/30 dev eth{eth}' in sh\nassert len(addresses)==114\nrouters={n['id']: 'r_'+re.sub('[^a-z0-9]+','_',n['name'].lower()).strip('_') for n in d['nodes']}\nfor idx,dev in routers.items():\n ip=f'10.200.0.{idx+1}'\n assert ip not in addresses;addresses.add(ip)\n assert f'ip -4 addr replace {ip}/32 dev lo' in (ROOT/(dev+'.startup')).read_text()\nassert len(addresses)==151\nroutes={dev:{} for dev in entries}\nfor r in route_rows:\n dev=r['source_device'];dest=r['destination'];nh=r['via'];eth=r['interface']\n assert dest not in routes[dev]\n routes[dev][dest]=r\n assert f'ip -4 route replace {dest} via {nh} dev {eth}' in (ROOT/(dev+'.startup')).read_text()\n # next hop belongs to point-to-point domain of the source router\n assert any(x[f'{side}_device']==dev and x[f'{side}_eth']==eth and x['target_ip' if side=='source' else 'source_ip']==nh for x in map_rows for side in ['source','target'])\nassert len(route_rows)==sum(57-len(v)+36 for v in entries.values())\n# Packet simulation according to the actual CSV forwarding entries.\naddr_dest={}\nfor r in map_rows:\n addr_dest[r['source_ip']]=r['subnet'];addr_dest[r['target_ip']]=r['subnet']\nfor n,dev in routers.items():addr_dest[f'10.200.0.{n+1}']=f'10.200.0.{n+1}/32'\nns_to_devs={r['subnet']:{r['source_device'],r['target_device']} for r in map_rows}\nloopdev={f'10.200.0.{n+1}/32':dev for n,dev in routers.items()}\nlookup={}\nfor r in map_rows:\n for side in ['source','target']:\n  dev=r[f'{side}_device'];ip=r['target_ip' if side=='source' else 'source_ip']\n  lookup[(dev,r[f'{side}_eth'],ip)]=r[f'{"target" if side=="source" else "source"}_device']\ncount=0\nfor start in entries:\n for addr,dest_net in addr_dest.items():\n  current=start;visited=set()\n  while True:\n   assert current not in visited, f'Routing loop: {start} -> {addr}'\n   visited.add(current)\n   if (dest_net in ns_to_devs and current in ns_to_devs[dest_net]) or (dest_net in loopdev and current==loopdev[dest_net]):break\n   assert dest_net in routes[current],f'Missing route {current}->{dest_net}'\n   entry=routes[current][dest_net]\n   current=lookup[(current,entry['interface'],entry['via'])]\n  count+=1\nprint(f'OK: {len(entries)} router, {len(map_rows)} link, {len(addresses)} IP unici, {len(route_rows)} rotte statiche, {count} simulazioni router->IP senza loop.')\nprint('Nota: verifica statica; avvio reale da verificare con Kathara + Docker.')\n'''
    save(OUT/'verify_lab.py',verify)
    # Disegno direttamente dai lat/lon; la topologia resta importata dal JSON.
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib import patheffects
        fig,ax=plt.subplots(figsize=(16,10))
        positions={n['id']: (n['pos'][0],n['pos'][1]) for n in nodes}
        for e in edges:
            a,b=positions[e['source']],positions[e['target']]
            ax.plot([a[0],b[0]],[a[1],b[1]], color='#7895AD',linewidth=1.3,alpha=0.75,zorder=1)
        for n in nodes:
            x,y=positions[n['id']]
            ax.scatter(x,y, s=55, c='#156D75', edgecolors='white', linewidths=0.6, zorder=3)
            label=ax.annotate(str(n['id'])+' '+n['name'],(x,y),xytext=(5,5),textcoords='offset points',fontsize=7.8,color='#263746',zorder=4)
            label.set_path_effects([patheffects.withStroke(linewidth=2.0,foreground='white')])
        ax.set_title('COST266 - backbone europeo | 37 router / 57 link',fontweight='bold',fontsize=17,pad=18)
        ax.set_xlabel('Longitudine');ax.set_ylabel('Latitudine')
        ax.set_xlim(-12,29);ax.set_ylim(34.5,64)
        ax.grid(alpha=.16,linewidth=.5)
        fig.tight_layout()
        fig.savefig(OUT/'topology.png',dpi=170,bbox_inches='tight')
        fig.savefig(OUT/'topology.svg',bbox_inches='tight')
        plt.close(fig)
    except ImportError:
        pass
    report=f'''# Report di verifica offline\n\n- Nodi analizzati: **37**\n- Collegamenti confrontati con `edges`: **57**\n- Domini punto-punto unici: **57**\n- Indirizzi WAN unici: **114**\n- Indirizzi loopback unici: **37**\n- Rotte statiche configurate: **{len(route_rows)}**\n- Cammini router->router controllati: **{37*37}**\n- Simulazioni router->indirizzo IP (114 WAN e 37 loopback): **{len(hops)}**, senza routing loop\n- Hop massimo nella simulazione (verso l'IP del subnet): **{max(hops)}**\n\n**Limite:** Kathara/Docker non disponibile in questo ambiente; non sono stati eseguiti `kathara check`, `kathara lstart` o ping reali.\n'''
    save(OUT/'VERIFICA_STATICA.md',report)
    print('Lab created at:',OUT)
    print('Routes:',len(route_rows),'Routing simulations:',len(hops),'Max hops:',max(hops))
    for u in [0,28,34]:
        print(names[u],[(ln['neighbor'],ln['idx'],ln['ip']) for ln in iface[u]])

if __name__=='__main__':
    main()
