Use only $kathara-creation for this task.

# T3 — Interpretazione della struttura — lab02_star7_mixed

Nel lab `lab02_star7_mixed` aggiungi un DNS interno gerarchico senza toccare la rete esistente. I ruoli da usare sono: root `pc2`, primario `test.` `pc3`, secondario `test.` `pc9`, autoritativo `services.test.` `pc12`, resolver `pc11`. Non ti vengono forniti gli IP: ricavali dalla configurazione del laboratorio e usa la famiglia corretta per ogni macchina.

La gerarchia deve essere reale: root `.` → `test.` con primario e secondario → `services.test.`; il secondario deve ricevere `test.` dal primario e il resolver deve partire solo dalla root interna, senza forwarder o DNS pubblici. In `test.` servono `www`, `portal` come alias di `www`, MX verso `mail.services.test.`, SRV HTTP e TXT `benchmark=dns-advanced`; in `services.test.` servono `mail` e `status`. Fai puntare `www.test.` ai server web `pc7` (IPv4) e `pc10` (IPv6) usando i record compatibili con le loro famiglie IP e `status.services.test.` a `pc1` (IPv4).

I client `pc4` (IPv4-only) e `pc6` (IPv6-only) devono interrogare soltanto `pc11` e raggiungere i servizi via DNS. Mantieni separati i ruoli, vieta soluzioni tramite `/etc/hosts`, non modificare `lab.conf`, indirizzi, gateway o routing e non aggiungere elementi di rete.
