# Lab 05: risoluzione DNS

Il DNS locale su r4 (10.15.5.1) risolve i nomi richiesti e pubblica i record MX per company.com e university.edu. Tutti i PC lo usano come resolver; gli indirizzi e le rotte della rete restano invariati. Il server non inoltra richieste a DNS esterni. I record MX indicano i destinatari della posta, ma non configurano un servizio di posta.

Avviare il laboratorio con `kathara lstart`. Per verificare da un PC remoto, eseguire separatamente:

```sh
kathara exec pc40 -- getent hosts ai.research.lab.net
kathara exec pc1 -- dig +short MX company.com
kathara exec pc40 -- dig +short MX university.edu
```
