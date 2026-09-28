# T5 — Autonomia elevata — lab03_ladder8_dual

Estendi `lab03_ladder8_dual` con un servizio DNS interno completo e gerarchico, mantenendo invariati topologia, indirizzamento e routing. Usa questa sola mappa dei ruoli: root `pc1`, primario `test.` `pc3`, secondario `test.` `pc5`, autoritativo `services.test.` `pc7`, resolver `pc9`. Tutto il resto va ricavato e progettato a partire dal laboratorio esistente.

In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; nessun’altra riga di `lab.conf` può essere modificata.

Il risultato deve includere root interna, delega e ridondanza per `test.`, sottozona `services.test.` e resolver ricorsivo interno. `www.test.` deve riferirsi a `pc13` per IPv4 e a `pc16` per IPv6; `portal.test.` deve essere un alias di `www.test.`. La posta di `test.` deve usare un MX con preferenza 10 verso `mail.services.test.`. Nella sottozona, `mail.services.test.` deve riferirsi a `pc7` e `status.services.test.` a `pc15`. Deve inoltre essere presente il TXT `benchmark=dns-advanced`. Ricava autonomamente indirizzi, famiglie IP, glue, nomi dei nameserver e configurazione BIND dai file del laboratorio.

I client `pc11` devono risolvere i nomi richiesti esclusivamente tramite il resolver, rispettando le famiglie IP esistenti. Non usare DNS pubblici, forwarder o `/etc/hosts` e non modificare la rete per far funzionare la soluzione.
