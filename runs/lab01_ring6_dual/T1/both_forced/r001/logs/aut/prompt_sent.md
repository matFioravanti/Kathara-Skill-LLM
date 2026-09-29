$kathara-creation
$kathara-dns

Prima di procedere, leggi esplicitamente entrambi i file:
- `.codex/skills/kathara-creation/SKILL.md`
- `.codex/skills/kathara-dns/SKILL.md`

Segui le istruzioni contenute nelle Skill pertinenti alla richiesta.

# Specifica DNS avanzata — lab01_ring6_dual

Nel laboratorio Kathara esistente `lab01_ring6_dual` va configurata una gerarchia DNS interna avanzata usando esclusivamente la topologia e gli indirizzi già presenti. Il lab contiene 6 router e 12 host; il routing statico IPv4/IPv6 deve restare invariato.

## Requisiti (MUST)

### Ruoli DNS
- `pc2` (`2001:db8:1100::10`): server autoritativo esclusivamente per la zona radice `.` raggiungibile via IPv6.
- `pc4` (`2001:db8:1100:1::10`): server primario autoritativo per la zona `test.` raggiungibile via IPv6.
- `pc6` (`2001:db8:1100:2::10`): server secondario autoritativo per `test.`; deve ottenere la zona da `pc4` tramite trasferimento di zona e non deve essere configurato come master.
- `pc8` (`2001:db8:1100:3::10`): server autoritativo esclusivamente per la sottozona `services.test.` raggiungibile via IPv6.
- `pc10` (`2001:db8:1100:4::10`): resolver ricorsivo per i client. Deve partire esclusivamente dalla root interna su `pc2`, seguire la delega verso `test.` e poi quella verso `services.test.`, senza forwarder.

### Delega e ridondanza
- La root su `pc2` deve delegare `test.` a entrambi i nameserver autoritativi `pc4` e `pc6`, con record NS `ns1.test.` e `ns2.test.` e glue AAAA verso `2001:db8:1100:1::10` e `2001:db8:1100:2::10`.
- `pc4` deve consentire il trasferimento della zona `test.` esclusivamente a `pc6`.
- `pc6` deve servire gli stessi dati autoritativi del primario.
- La zona `test.` deve delegare `services.test.` a `pc8` tramite `ns.services.test.` e glue AAAA verso `2001:db8:1100:3::10`.

### Record della zona `test.`
- Crea `www.test. A 10.11.5.10`.
- Crea `www.test. AAAA 2001:db8:1100:3::10`.
- Crea `portal.test. CNAME www.test.`.
- Crea un record MX per `test.` con preferenza `10` verso `mail.services.test.`.
- Crea `test. TXT "benchmark=dns-advanced"`.

### Record della zona `services.test.`
- Crea `mail.services.test. AAAA 2001:db8:1100:3::10`.
- Crea `status.services.test. AAAA 2001:db8:1100:2::10`.
- La zona deve essere servita soltanto dal server autoritativo assegnato alla sottozona.

### Resolver
- Configura `pc10` con una zona root di tipo hint che punti esclusivamente alla root interna `2001:db8:1100::10`; non inserire root server pubblici.
- Non configurare forwarder.
- Imposta `dnssec-validation no;`.
- Il resolver deve seguire realmente le deleghe interne e non deve essere autoritativo per `.`, `test.` o `services.test.`.

### Client
- `pc12` (`2001:db8:1100:5::10`) usa il resolver `pc10` via IPv6 (`2001:db8:1100:4::10`); deve risolvere tutti i record richiesti.
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
- `pc4` non deve essere root, resolver ricorsivo o autoritativo per `services.test.`.
- `pc6` deve essere secondario per `test.` e non deve essere configurato come master o resolver.
- `pc8` non deve essere autoritativo per `.` o `test.` e non deve offrire ricorsione.
- `pc10` non deve essere autoritativo per `.`, `test.` o `services.test.`.

### Client
- I client devono interrogare `pc10` e non i server autoritativi direttamente.
- `pc12` deve restare IPv6-only; non aggiungere configurazioni dell'altra famiglia IP per aggirare i requisiti.
