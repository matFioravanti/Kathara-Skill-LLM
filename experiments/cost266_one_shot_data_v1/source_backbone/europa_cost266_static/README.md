# Laboratorio Kathara - COST266 Europa, routing statico

Topologia europea ricostruita fedelmente dal file `cost266.json` usando **37 router** e **57 collegamenti**.
Ogni città e' un router (`r_rome`, `r_paris`, ecc.); ogni edge e' un dominio di collisione
punto-punto distinto. Nessun router, switch o collegamento di backbone e' stato inventato.

## Piano IP

- WAN: `10.100.0.0/24`, suddivisa in **57 sottoreti /30**, una per ogni edge nell'ordine del JSON.
- Ogni router ha una loopback `/32` `10.200.0.(id+1)` per ping, traceroute e benchmark.
- Non ci sono indirizzi duplicati e ogni router ha `net.ipv4.ip_forward=1`.
- IPv6 disabilitato.
- Routing STATICO completo, con pesi Dijkstra = `dist` del JSON; nessun OSPF/BGP/RIP.

Vedi `topology_mapping.csv` per collegamenti / interface / IP; `routing_table.csv` per tutte
le rotte, `shortest_paths.csv` per i 1.369 percorsi tra coppie di città.

## Requisiti

Kathara e Docker installati e avviati; risorse sufficienti a eseguire contemporaneamente
37 container. L'immagine usata per i router e' `kathara/core`.

## Avvio sul tuo computer

```bash
cd europa_cost266_static
python3 verify_lab.py           # verifica statica senza Docker
kathara check                  # ambiente Kathara e Docker
kathara lstart --print         # controllo preliminare di lab.conf (nessun avvio)
kathara lstart --noterminals   # avvio dei 37 router
kathara linfo                  # lista router attivi
```

## Esempi di test dinamici

Roma: COST266 id=28, loopback `10.200.0.29`. Amsterdam: id=0, loopback `10.200.0.1`.

```bash
kathara exec r_rome -- ip -4 addr show
kathara exec r_rome -- ip -4 route show
kathara exec r_rome -- ping -c 3 10.200.0.1
kathara exec r_amsterdam -- ping -c 3 10.200.0.29
kathara exec r_rome -- traceroute -n 10.200.0.1
kathara lclean
```

Per verificare l'intera matrice di ping inter-router (1.332 test), puoi usare
`python3 runtime_ping.py` dal computer host **dopo** l'avvio del laboratorio.

## Uso per la tesi DNS

Questo ZIP rappresenta il backbone base di routing statico. **Non include
server BIND, resolver o client DNS**: per creare gli scenari DNS occorre
prima aggiungere host e LAN d'accesso in una variante del laboratorio; successivamente
la skill `kathara-dns` puo' configurare tali host preservando indirizzi, rotte e link.
I dati `demands` e `ecmp_*` originali rimangono nel JSON per eventuali analisi,
ma non sono configurazioni di rete immediatamente eseguibili.

## Verifica

Il generatore ha controllato staticamente 5587 percorsi router→IP (114 indirizzi
WAN e 37 loopback), inclusa assenza di loop di next-hop. Ciò NON sostituisce
una prova effettiva con `kathara lstart`: la verifica dinamica richiede Kathara
e Docker sul tuo computer.

La sintassi `lab.conf` segue la SkillCreazione e la [documentazione ufficiale](https://www.kathara.org/man-pages/kathara-lab.conf.5.html).
