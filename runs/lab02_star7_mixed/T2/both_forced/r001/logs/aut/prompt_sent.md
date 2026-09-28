Use $kathara-creation and $kathara-dns for this task.

# T2 — Configurazione guidata — lab02_star7_mixed

Completa il laboratorio Kathara `lab02_star7_mixed` aggiungendo la gerarchia DNS e i servizi HTTP richiesti, senza modificare topologia, indirizzamento, gateway o routing statico esistenti.

Usa questa assegnazione dei ruoli:
- `pc2`: autoritativo esclusivo per la root `.`;
- `pc3`: primario autoritativo per `test.`;
- `pc9`: secondario autoritativo per `test.` tramite trasferimento dal primario;
- `pc12`: autoritativo esclusivo per `services.test.`;
- `pc11`: resolver ricorsivo per i client.

Ricava dagli `.startup` gli indirizzi e la famiglia IP corretti. La root deve delegare `test.` ai due autoritativi con i glue coerenti; `test.` deve delegare `services.test.` al relativo server. Il trasferimento della zona `test.` deve essere permesso soltanto al secondario.

Nella zona `test.` devono esistere:
- `www.test.` con record A verso il server HTTP IPv4 `pc7`;
- `www.test.` con record AAAA verso il server HTTP IPv6 `pc10`;
- `portal.test.` come CNAME di `www.test.`;
- MX di `test.` con preferenza 10 verso `mail.services.test.`;
- `_http._tcp.test.` come SRV `0 5 80 www.test.`;
- TXT `benchmark=dns-advanced`.

In `services.test.`, `mail.services.test.` deve puntare al server `pc12` e `status.services.test.` al server HTTP dedicato `pc1`.

Configura `pc11` senza forwarder e senza DNS pubblici: deve partire esclusivamente dalla root interna, avere `dnssec-validation no;` e seguire realmente le deleghe. I client `pc4` (IPv4-only) e `pc6` (IPv6-only) devono usare soltanto questo resolver.

Attiva i servizi HTTP coerenti con i record: `www.test.` su `pc7` via IPv4; `www.test.` su `pc10` via IPv6; `status.services.test.` su `pc1` via IPv4.

Non usare `/etc/hosts` per simulare il DNS, non configurare i router come DNS, non combinare più ruoli DNS sulla stessa macchina e non aggiungere indirizzi, interfacce o rotte.
