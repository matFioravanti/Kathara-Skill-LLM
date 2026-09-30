$kathara-dns

Prima di procedere, leggi esplicitamente il file
`.codex/skills/kathara-dns/SKILL.md`
e segui le istruzioni contenute nella Skill.

# T3 — Interpretazione della struttura — lab03_ladder8_dual

Nel lab `lab03_ladder8_dual` aggiungi un DNS interno gerarchico senza toccare la rete esistente. I ruoli da usare sono: root `pc1`, primario `test.` `pc3`, secondario `test.` `pc5`, autoritativo `services.test.` `pc7`, resolver `pc9`. Non ti vengono forniti gli IP: ricavali dalla configurazione del laboratorio e usa la famiglia corretta per ogni macchina.

La gerarchia deve essere reale: root `.` → `test.` con primario e secondario → `services.test.`; il secondario deve ricevere `test.` dal primario e il resolver deve partire solo dalla root interna, senza forwarder o DNS pubblici. In `test.` servono `www`, `portal` come alias di `www`, MX verso `mail.services.test.` e TXT `benchmark=dns-advanced`; in `services.test.` servono `mail` e `status`. Fai puntare `www.test.` agli host `pc13` (IPv4) e `pc16` (IPv6) usando i record compatibili con le loro famiglie IP e `status.services.test.` a `pc15` (IPv4).

I client `pc11` (IPv4-only) devono interrogare soltanto `pc9` e risolvere tutti i nomi richiesti tramite il resolver. Mantieni separati i ruoli, vieta soluzioni tramite `/etc/hosts`, in `lab.conf` puoi modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; non modificare nessun’altra riga di `lab.conf`, né indirizzi, gateway o routing, e non aggiungere elementi di rete.
