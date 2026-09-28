Use only $kathara-dns for this task.

# Specifica DNS: gerarchia interna per il lab static-routing

Nel laboratorio Kathara esistente va configurata una gerarchia DNS interna usando la topologia e gli indirizzi già presenti. Il lab contiene cinque router (`r1`–`r5`) e gli host `pc1`–`pc6`; il routing è statico e deve restare invariato.

## Requisiti (MUST)

### Ruoli e zone
- `pc2` (`100.0.6.2`): server autoritativo esclusivamente per la zona radice `.`.
- `pc5` (`100.0.8.2`): server autoritativo esclusivamente per la zona `test.`, delegata dalla root servita da `pc2` tramite record NS e glue IPv4 per `pc5`.
- `pc3` (`100.0.0.2`, `2001:8::2`): resolver ricorsivo per i client. Deve raggiungere la root interna su `pc2` usando root hints, senza forwarder.
- `pc1` (`200.0.1.2`): web server HTTP raggiungibile all'indirizzo `http://200.0.1.2/`.

### Record DNS
- La zona `test.` su `pc5` deve contenere `www.test. A 200.0.1.2`.
- La root su `pc2` deve delegare `test.` a `pc5` con il record NS e il glue A necessario per raggiungere `100.0.8.2`.
- Configura `pc3` con una zona root di tipo hint che indirizzi la root interna su `100.0.6.2`; non inserire root server pubblici o indirizzi AAAA per la root.
- Su `pc3` disattiva la validazione DNSSEC con `dnssec-validation no;`.

### Client e verifica del servizio
- `pc4` usa `pc3` come resolver tramite `100.0.0.2`; deve risolvere `www.test.` via DNS e poter raggiungere il web server IPv4.
- `pc6` è IPv6-only e usa `pc3` tramite `2001:8::2`; deve risolvere il record A di `www.test.` attraverso il resolver. Non aggiungere record AAAA o configurazioni di rete per simulare una connettività IPv6 al web server.
- Verifica che il servizio HTTP di `pc1` risponda con stato 200 su `http://200.0.1.2/`.

## Vincoli (MUST NOT)

### Vincoli generali
- Non modificare `lab.conf`, la topologia, il routing statico, i gateway o gli indirizzi IP già assegnati.
- Non aggiungere host, link, interfacce, indirizzi o rotte.
- Non usare forwarder, DNS pubblici o root hint pubblici.
- Non configurare risposte statiche in `/etc/hosts` per `www.test.`.
- Non assegnare più ruoli DNS alla stessa macchina e non configurare i router come server DNS.

### `pc2` — Root DNS
- Non deve essere autoritativo per `test.`.
- Non deve offrire ricorsione ai client.

### `pc5` — Autoritativo per `test.`
- Non deve essere configurato come root DNS o resolver ricorsivo.
- Non deve essere autoritativo per la zona radice `.`.

### `pc3` — Resolver
- Non deve essere autoritativo per `.` né per `test.`.
- Non deve usare forwarder o configurazioni che aggirino la delega interna.

### Client
- I client devono interrogare `pc3`, non `pc2` o `pc5` direttamente.
- `pc6` deve restare IPv6-only e senza route IPv6 predefinita.
