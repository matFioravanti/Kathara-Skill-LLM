# Specifica strutturata - Kathara SkillCreazione

- **Directory:** `europa_cost266_static/`
- **Nome:** `europa_cost266_static`
- **Sorgente dati:** `cost266.json` (COST266/TopoHub).
- **Topologia:** 37 router con nomi `r_<city>` e 57 domini di collisione distinti, uno per ciascun link originale. Nessuna nuova interconnessione.
- **Indirizzamento:** IPv4 statico: 57 sottoreti /30 successive di `10.100.0.0/24`; indirizzo .1 lato source e .2 lato target in ordine del JSON. Loopback /32 `10.200.0.(id+1)`.
- **Routing:** completamente statico. Cammini minimi Dijkstra pesati con campo `dist`; rotta /32 per ogni altra loopback; rotta /30 per ogni link non direttamente connesso, scelta verso l'estremita' piu' vicina. In caso di pari costo, spareggio per path di ID lessicograficamente minore.
- **Immagine:** `kathara/core`; nessun demone di routing. IPv6 disabilitato.
- **File richiesti:** `lab.conf`, 37 `<router>.startup`, `README.md`, CSV di collegamenti e rotte, JSON originale, strumenti di verifica.
- **Verifica progettata:** corrispondenza dei nodi e link, unicita' degli IP e domini, route-next-hop adiacenti, nessun loop su ciascuna delle 37*151 = 5587 coppie router/IP, prova dinamica esterna con Kathara.
- **Assunzioni:** topologia BASE senza host DNS; la fase DNS e' una variante successiva con host e link di accesso da aggiungere prima dell'applicazione della skill DNS. `demands` ed `ecmp_*` non sono convertiti in link o router.
