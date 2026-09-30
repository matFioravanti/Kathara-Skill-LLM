$kathara-dns

Prima di procedere, leggi esplicitamente il file
`.codex/skills/kathara-dns/SKILL.md`
e segui le istruzioni contenute nella Skill.

# T5 — Autonomia elevata — lab01_ring6_dual

Estendi `lab01_ring6_dual` con un servizio DNS interno completo e gerarchico, mantenendo invariati topologia, indirizzamento e routing. Usa questa sola mappa dei ruoli: root `pc2`, primario `test.` `pc4`, secondario `test.` `pc6`, autoritativo `services.test.` `pc8`, resolver `pc10`. Tutto il resto va ricavato e progettato a partire dal laboratorio esistente.

In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; nessun’altra riga di `lab.conf` può essere modificata.

Il risultato deve includere root interna, delega e ridondanza per `test.`, sottozona `services.test.` e resolver ricorsivo interno. `www.test.` deve riferirsi a `pc11` per IPv4 e a `pc8` per IPv6; `portal.test.` deve essere un alias di `www.test.`. La posta di `test.` deve usare un MX con preferenza 10 verso `mail.services.test.`. Nella sottozona, `mail.services.test.` deve riferirsi a `pc8` e `status.services.test.` a `pc6`. Deve inoltre essere presente il TXT `benchmark=dns-advanced`. Ricava autonomamente indirizzi, famiglie IP, glue, nomi dei nameserver e configurazione BIND dai file del laboratorio.

I client `pc12` devono risolvere i nomi richiesti esclusivamente tramite il resolver, rispettando le famiglie IP esistenti. Non usare DNS pubblici, forwarder o `/etc/hosts` e non modificare la rete per far funzionare la soluzione.
