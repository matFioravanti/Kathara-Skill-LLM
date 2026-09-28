# T2 — Configurazione guidata — lab01_ring6_dual

Completa il laboratorio Kathara `lab01_ring6_dual` aggiungendo la gerarchia DNS e i servizi HTTP richiesti, senza modificare topologia, indirizzamento, gateway o routing statico esistenti.

Usa questa assegnazione dei ruoli:
- `pc2`: autoritativo esclusivo per la root `.`;
- `pc4`: primario autoritativo per `test.`;
- `pc6`: secondario autoritativo per `test.` tramite trasferimento dal primario;
- `pc8`: autoritativo esclusivo per `services.test.`;
- `pc10`: resolver ricorsivo per i client.

Ricava dagli `.startup` gli indirizzi e la famiglia IP corretti. La root deve delegare `test.` ai due autoritativi con i glue coerenti; `test.` deve delegare `services.test.` al relativo server. Il trasferimento della zona `test.` deve essere permesso soltanto al secondario.

Nella zona `test.` devono esistere:
- `www.test.` con record A verso il server HTTP IPv4 `pc11`;
- `www.test.` con record AAAA verso il server HTTP IPv6 `pc8`;
- `portal.test.` come CNAME di `www.test.`;
- MX di `test.` con preferenza 10 verso `mail.services.test.`;
- `_http._tcp.test.` come SRV `0 5 80 www.test.`;
- TXT `benchmark=dns-advanced`.

In `services.test.`, `mail.services.test.` deve puntare al server `pc8` e `status.services.test.` al server HTTP dedicato `pc6`.

Configura `pc10` senza forwarder e senza DNS pubblici: deve partire esclusivamente dalla root interna, avere `dnssec-validation no;` e seguire realmente le deleghe. I client `pc12` (IPv6-only) devono usare soltanto questo resolver.

Attiva i servizi HTTP coerenti con i record: `www.test.` su `pc11` via IPv4; `www.test.` su `pc8` via IPv6; `status.services.test.` su `pc6` via IPv6.

Non usare `/etc/hosts` per simulare il DNS, non configurare i router come DNS, non combinare più ruoli DNS sulla stessa macchina e non aggiungere indirizzi, interfacce o rotte.
