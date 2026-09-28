Use $kathara-creation and $kathara-dns for this task.

Nel laboratorio Kathara esistente, `pc4` e `pc6` devono poter risolvere `www.test.` passando da `pc3`, senza conoscere o interrogare direttamente i server autoritativi.

La catena DNS deve partire dalla root interna su `pc2` (`100.0.6.2`), che delega `test.` a `pc5` (`100.0.8.2`). La zona `test.` deve contenere il record A `www.test. → 200.0.1.2`. `pc3` (`100.0.0.2` e `2001:8::2`) svolge la ricorsione tramite root hint interna e senza forwarder. `pc4` usa il resolver via IPv4; `pc6`, che è solo IPv6, lo usa via IPv6. Il web server su `pc1` (`200.0.1.2`) deve rispondere via HTTP su `http://200.0.1.2/`.

Mantieni separati i ruoli DNS, disattiva la validazione DNSSEC sul resolver con `dnssec-validation no;` e non usare infrastrutture DNS esterne. Non modificare topologia, indirizzi, gateway o routing statico. Non aggiungere un record AAAA o una connettività IPv6 al web server: il requisito IPv6 riguarda il collegamento DNS da `pc6` a `pc3`.
