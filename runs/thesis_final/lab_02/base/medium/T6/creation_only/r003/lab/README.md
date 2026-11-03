# Gerarchia DNS del laboratorio

I server autorevoli pc1–pc31 ospitano le zone indicate nella richiesta; pc1 è la radice. pc32 (10.15.8.14) è il resolver ricorsivo, configurato con la sola radice del laboratorio. Tutti i PC lo usano come nameserver. pc33 (10.15.9.11) ospita Apache ed è il destinatario di `www.example.com`. La risoluzione riguarda la gerarchia locale, non il DNS pubblico.

Avviare con `kathara lstart`. Per una verifica, eseguire da un client `dig @10.15.8.14 www.example.com` e interrogare anche `ai.research.lab.net` e gli MX di `company.com`. Una query diretta a un autorevole, ad esempio `dig @10.15.1.11 com NS +norecurse`, mostra la delega.
