Use only $kathara-dns for this task.

Nel laboratorio Kathara esistente configura il DNS gerarchico interno rispettando la topologia a cinque router e il routing statico già presenti.

Fai:
- Configura `pc2` (`100.0.6.2`) come server autoritativo per la sola zona radice `.`.
- Configura `pc5` (`100.0.8.2`) come server autoritativo per la sola zona `test.` e delega `test.` dalla root con record NS e glue A verso `100.0.8.2`.
- Configura `pc3` (`100.0.0.2`, `2001:8::2`) come resolver ricorsivo che usa una root hint interna verso `pc2`, senza forwarder e con `dnssec-validation no;`.
- Nella zona `test.` crea il record `www.test. A 200.0.1.2`.
- Mantieni attivo il web server su `pc1` (`200.0.1.2`) e verifica la risposta HTTP su `http://200.0.1.2/`.
- Configura `pc4` per usare il resolver `pc3` via IPv4 (`100.0.0.2`) e `pc6`, IPv6-only, per usarlo via IPv6 (`2001:8::2`). Entrambi devono risolvere `www.test.` attraverso la gerarchia DNS interna.

Non fare:
- Non modificare topologia, `lab.conf`, indirizzi, gateway o routing statico; non aggiungere interfacce o rotte.
- Non usare forwarder, DNS pubblici o root hint pubblici.
- Non rendere `pc2` autoritativo per `test.` o ricorsivo; non rendere `pc5` root o ricorsivo; non rendere `pc3` autoritativo.
- Non far interrogare direttamente ai client `pc2` o `pc5`.
- Non aggiungere record AAAA per `www.test.` né risposte in `/etc/hosts`; `pc6` deve restare IPv6-only e senza route IPv6 predefinita.
