$kathara-creation
$kathara-dns

Prima di procedere, leggi esplicitamente entrambi i file:
- `.codex/skills/kathara-creation/SKILL.md`
- `.codex/skills/kathara-dns/SKILL.md`

Segui le istruzioni contenute nelle Skill pertinenti alla richiesta.

# T5 — Autonomia elevata — lab02_star7_mixed

Estendi `lab02_star7_mixed` con un servizio DNS interno completo e gerarchico, mantenendo invariati topologia, indirizzamento e routing. Usa questa sola mappa dei ruoli: root `pc2`, primario `test.` `pc3`, secondario `test.` `pc9`, autoritativo `services.test.` `pc12`, resolver `pc11`. Tutto il resto va ricavato e progettato a partire dal laboratorio esistente.

In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; nessun’altra riga di `lab.conf` può essere modificata.

Il risultato deve includere root interna, delega e ridondanza per `test.`, sottozona `services.test.` e resolver ricorsivo interno. `www.test.` deve riferirsi a `pc7` per IPv4 e a `pc10` per IPv6; `portal.test.` deve essere un alias di `www.test.`. La posta di `test.` deve usare un MX con preferenza 10 verso `mail.services.test.`. Nella sottozona, `mail.services.test.` deve riferirsi a `pc12` e `status.services.test.` a `pc1`. Deve inoltre essere presente il TXT `benchmark=dns-advanced`. Ricava autonomamente indirizzi, famiglie IP, glue, nomi dei nameserver e configurazione BIND dai file del laboratorio.

I client `pc4`, `pc6` devono risolvere i nomi richiesti esclusivamente tramite il resolver, rispettando le famiglie IP esistenti. Non usare DNS pubblici, forwarder o `/etc/hosts` e non modificare la rete per far funzionare la soluzione.
