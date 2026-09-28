Use only $kathara-dns for this task.

# T4 — Progettazione vincolata — lab01_ring6_dual

Completa `lab01_ring6_dual` con una infrastruttura DNS interna gerarchica e ridondata. Mantieni integralmente la rete e il routing esistenti e ricava autonomamente indirizzi e famiglie IP dai file del lab.

In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; nessun’altra riga di `lab.conf` può essere modificata.

Vincolo di assegnazione: root `pc2`, primario `test.` `pc4`, secondario `test.` `pc6`, autoritativo `services.test.` `pc8`, resolver `pc10`. La soluzione deve avere una root interna, `test.` delegata a primario+secondario, `services.test.` delegata separatamente, trasferimento di zona al solo secondario e un resolver ricorsivo che non usi forwarder né infrastruttura DNS pubblica.

Pubblica `www.test.` facendo riferimento a `pc11` tramite IPv4 e a `pc8` tramite IPv6; `portal.test.` deve essere un alias di `www.test.`. Configura per `test.` un record MX con preferenza 10 verso `mail.services.test.` e il TXT `benchmark=dns-advanced`. Nella zona `services.test.`, `mail.services.test.` deve riferirsi a `pc8` e `status.services.test.` a `pc6`. Ricava autonomamente dai file del laboratorio gli indirizzi e i tipi di record compatibili con le famiglie IP dei dispositivi indicati.

I client `pc12` devono usare soltanto il resolver assegnato rispettando la famiglia IP già prevista per ciascuno.

Non aggirare i requisiti con `/etc/hosts`, indirizzi o rotte aggiuntive e non mescolare i ruoli DNS.
