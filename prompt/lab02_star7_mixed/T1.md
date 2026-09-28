# Specifica DNS avanzata — lab02_star7_mixed

Nel laboratorio Kathara esistente `lab02_star7_mixed` va configurata una gerarchia DNS interna avanzata usando esclusivamente la topologia e gli indirizzi già presenti. Il lab contiene 7 router e 12 host; il routing statico IPv4/IPv6 deve restare invariato.

## Requisiti (MUST)

### Ruoli DNS
- `pc2` (`192.168.32.11`): server autoritativo esclusivamente per la zona radice `.` raggiungibile via IPv4.
- `pc3` (`2001:db8:1200:1::10`): server primario autoritativo per la zona `test.` raggiungibile via IPv6.
- `pc9` (`2001:db8:1200:4::10`): server secondario autoritativo per `test.`; deve ottenere la zona da `pc3` tramite trasferimento di zona e non deve essere configurato come master.
- `pc12` (`192.168.34.139`): server autoritativo esclusivamente per la sottozona `services.test.` raggiungibile via IPv4.
- `pc11` (`192.168.34.138`, `2001:db8:1200:5::10`): resolver ricorsivo per i client. Deve partire esclusivamente dalla root interna su `pc2`, seguire la delega verso `test.` e poi quella verso `services.test.`, senza forwarder.

### Delega e ridondanza
- La root su `pc2` deve delegare `test.` a entrambi i nameserver autoritativi `pc3` e `pc9`, con record NS `ns1.test.` e `ns2.test.` e glue AAAA verso `2001:db8:1200:1::10` e `2001:db8:1200:4::10`.
- `pc3` deve consentire il trasferimento della zona `test.` esclusivamente a `pc9`.
- `pc9` deve servire gli stessi dati autoritativi del primario.
- La zona `test.` deve delegare `services.test.` a `pc12` tramite `ns.services.test.` e glue A verso `192.168.34.139`.

### Record della zona `test.`
- Crea `www.test. A 192.168.33.138`.
- Crea `www.test. AAAA 2001:db8:1200:4::11`.
- Crea `portal.test. CNAME www.test.`.
- Crea un record MX per `test.` con preferenza `10` verso `mail.services.test.`.
- Crea `test. TXT "benchmark=dns-advanced"`.

### Record della zona `services.test.`
- Crea `mail.services.test. A 192.168.34.139`.
- Crea `status.services.test. A 192.168.32.10`.
- La zona deve essere servita soltanto dal server autoritativo assegnato alla sottozona.

### Resolver
- Configura `pc11` con una zona root di tipo hint che punti esclusivamente alla root interna `192.168.32.11`; non inserire root server pubblici.
- Non configurare forwarder.
- Imposta `dnssec-validation no;`.
- Il resolver deve seguire realmente le deleghe interne e non deve essere autoritativo per `.`, `test.` o `services.test.`.

### Client
- `pc4` (`192.168.32.138`) usa il resolver `pc11` via IPv4 (`192.168.34.138`); deve risolvere tutti i record richiesti.
- `pc6` (`2001:db8:1200:2::11`) usa il resolver `pc11` via IPv6 (`2001:db8:1200:5::10`); deve risolvere tutti i record richiesti.
- I client devono risolvere anche `portal.test.`, il record MX di `test.`, il TXT e i nomi della sottozona `services.test.` tramite il resolver.

## Vincoli (MUST NOT)

### Vincoli generali
- In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; non modificare nessun’altra riga di `lab.conf`.
- Non modificare topologia, collision domain, indirizzi, gateway o routing statico.
- Non aggiungere host, link, interfacce, indirizzi o rotte.
- Non usare forwarder, DNS pubblici o root hint pubblici.
- Non inserire `www.test.`, `portal.test.`, `mail.services.test.` o `status.services.test.` in `/etc/hosts`.
- Non configurare i router come server DNS.
- Non assegnare a una macchina più ruoli DNS tra root, primario `test.`, secondario `test.`, autoritativo `services.test.` e resolver.

### Separazione dei ruoli
- `pc2` non deve essere autoritativo per `test.` o `services.test.` e non deve offrire ricorsione.
- `pc3` non deve essere root, resolver ricorsivo o autoritativo per `services.test.`.
- `pc9` deve essere secondario per `test.` e non deve essere configurato come master o resolver.
- `pc12` non deve essere autoritativo per `.` o `test.` e non deve offrire ricorsione.
- `pc11` non deve essere autoritativo per `.`, `test.` o `services.test.`.

### Client
- I client devono interrogare `pc11` e non i server autoritativi direttamente.
- `pc4` deve restare IPv4-only; `pc6` deve restare IPv6-only; non aggiungere configurazioni dell'altra famiglia IP per aggirare i requisiti.
