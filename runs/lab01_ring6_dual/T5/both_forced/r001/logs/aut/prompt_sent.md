Use $kathara-creation and $kathara-dns for this task.

# T5 — Autonomia elevata — lab01_ring6_dual

Estendi `lab01_ring6_dual` con un servizio DNS interno completo e gerarchico, mantenendo invariati topologia, indirizzamento e routing. Usa questa sola mappa dei ruoli: root `pc2`, primario `test.` `pc4`, secondario `test.` `pc6`, autoritativo `services.test.` `pc8`, resolver `pc10`. Tutto il resto va ricavato e progettato a partire dal laboratorio esistente.

Il risultato deve includere root interna, delega e ridondanza per `test.`, sottozona `services.test.`, resolver ricorsivo interno, i nomi `www.test.`, `portal.test.`, `mail.services.test.` e `status.services.test.`, oltre ai record MX/SRV/TXT necessari e ai servizi HTTP coerenti. I client `pc12` devono risolvere e usare i servizi esclusivamente tramite il resolver, rispettando le famiglie IP esistenti. Non usare DNS pubblici, forwarder o `/etc/hosts` e non modificare la rete per far funzionare la soluzione.
