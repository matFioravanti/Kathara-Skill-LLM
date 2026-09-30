$kathara-dns

Prima di procedere, leggi esplicitamente il file
`.codex/skills/kathara-dns/SKILL.md`
e segui le istruzioni contenute nella Skill.

# T2 — Configurazione guidata — lab03_ladder8_dual

Completa il laboratorio Kathara `lab03_ladder8_dual` aggiungendo la gerarchia DNS richiesta, senza modificare topologia, indirizzamento, gateway o routing statico esistenti.

In `lab.conf` è consentito modificare esclusivamente le direttive `<device>[image]` dei dispositivi che svolgono un ruolo DNS; nessun’altra riga di `lab.conf` può essere modificata.

Usa questa assegnazione dei ruoli:
- `pc1`: autoritativo esclusivo per la root `.`;
- `pc3`: primario autoritativo per `test.`;
- `pc5`: secondario autoritativo per `test.` tramite trasferimento dal primario;
- `pc7`: autoritativo esclusivo per `services.test.`;
- `pc9`: resolver ricorsivo per i client.

Ricava dagli `.startup` gli indirizzi e la famiglia IP corretti. La root deve delegare `test.` ai due autoritativi con i glue coerenti; `test.` deve delegare `services.test.` al relativo server. Il trasferimento della zona `test.` deve essere permesso soltanto al secondario.

Nella zona `test.` devono esistere:
- `www.test.` con record A verso `pc13`;
- `www.test.` con record AAAA verso `pc16`;
- `portal.test.` come CNAME di `www.test.`;
- MX di `test.` con preferenza 10 verso `mail.services.test.`;
- TXT `benchmark=dns-advanced`.

In `services.test.`, `mail.services.test.` deve puntare al server `pc7` e `status.services.test.` a `pc15`.

Configura `pc9` senza forwarder e senza DNS pubblici: deve partire esclusivamente dalla root interna, avere `dnssec-validation no;` e seguire realmente le deleghe. I client `pc11` (IPv4-only) devono usare soltanto questo resolver.


Non usare `/etc/hosts` per simulare il DNS, non configurare i router come DNS, non combinare più ruoli DNS sulla stessa macchina e non aggiungere indirizzi, interfacce o rotte.
