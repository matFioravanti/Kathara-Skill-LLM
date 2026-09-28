Use $kathara-creation and $kathara-dns for this task.

Ho già un laboratorio Kathara con cinque router, routing statico e gli host `pc1`–`pc6`. Voglio aggiungere una gerarchia DNS interna senza cambiare la rete. `pc2` (`100.0.6.2`) deve essere la root autoritativa per `.`; `pc5` (`100.0.8.2`) deve gestire soltanto `test.`, delegata dalla root con NS e glue A corretti. In quella zona crea `www.test. A 200.0.1.2`; il web server è `pc1` e risponde su `http://200.0.1.2/`.

I client devono chiedere i nomi a `pc3` (`100.0.0.2`, `2001:8::2`), che risolve partendo dalla root hint interna su `pc2`. Non configurare forwarder e imposta `dnssec-validation no;`. `pc4` deve usare il resolver via IPv4; `pc6`, che è IPv6-only, via IPv6. Entrambi devono ottenere la risoluzione DNS di `www.test.`. Il record web è soltanto A, quindi non aggiungere AAAA o configurazioni per rendere raggiungibile il server via IPv6.

Non assegnare più ruoli alla stessa macchina, non usare DNS pubblici e non modificare topologia, indirizzi, gateway o routing statico. Non aggiungere host, rotte o voci statiche per `www.test.` in `/etc/hosts`.
