Use only $kathara-dns for this task.

# T4 — Progettazione vincolata — lab02_star7_mixed

Completa `lab02_star7_mixed` con una infrastruttura DNS interna gerarchica e ridondata. Mantieni integralmente la rete e il routing esistenti e ricava autonomamente indirizzi e famiglie IP dai file del lab.

Vincolo di assegnazione: root `pc2`, primario `test.` `pc3`, secondario `test.` `pc9`, autoritativo `services.test.` `pc12`, resolver `pc11`. La soluzione deve avere una root interna, `test.` delegata a primario+secondario, `services.test.` delegata separatamente, trasferimento di zona al solo secondario e un resolver ricorsivo che non usi forwarder né infrastruttura DNS pubblica.

Pubblica `www.test.`, `portal.test.`, posta per `test.`, discovery HTTP via SRV, il TXT `benchmark=dns-advanced`, `mail.services.test.` e `status.services.test.`. I server HTTP previsti dal lab devono essere raggiungibili con questi nomi; i client `pc4`, `pc6` devono usare soltanto il resolver assegnato rispettando la famiglia IP già prevista per ciascuno.

Non aggirare i requisiti con `/etc/hosts`, indirizzi o rotte aggiuntive e non mescolare i ruoli DNS.
