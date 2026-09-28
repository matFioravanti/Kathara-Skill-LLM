# T5 — Autonomia elevata — lab02_star7_mixed

Estendi `lab02_star7_mixed` con un servizio DNS interno completo e gerarchico, mantenendo invariati topologia, indirizzamento e routing. Usa questa sola mappa dei ruoli: root `pc2`, primario `test.` `pc3`, secondario `test.` `pc9`, autoritativo `services.test.` `pc12`, resolver `pc11`. Tutto il resto va ricavato e progettato a partire dal laboratorio esistente.

Il risultato deve includere root interna, delega e ridondanza per `test.`, sottozona `services.test.`, resolver ricorsivo interno, i nomi `www.test.`, `portal.test.`, `mail.services.test.` e `status.services.test.`, oltre ai record MX/SRV/TXT necessari e ai servizi HTTP coerenti. I client `pc4`, `pc6` devono risolvere e usare i servizi esclusivamente tramite il resolver, rispettando le famiglie IP esistenti. Non usare DNS pubblici, forwarder o `/etc/hosts` e non modificare la rete per far funzionare la soluzione.
