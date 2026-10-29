# Lab 01 — Catena lineare, routing IPv4 statico, senza DNS

- 4 router: r1 → r2 → r3 → r4; 20 PC suddivisi in LAN A1–A4.
- Tre collegamenti tra router: B12, B23, B34.
- Indirizzi IPv4, rotte statiche (18) e gateway dei PC (20) **immutati**.
- Nessun server DNS, configurazione BIND, resolver o protocollo di routing dinamico.

## Mitigazione dei ping isolati falliti nel checker

Il checker aveva segnalato 617/620, con fallimenti ICMP isolati pc4→pc17, pc16→pc10 e pc19→pc7. I file di routing erano coerenti; per ridurre i timeout iniziali causati dalla risoluzione ARP, gli startup ora impostano **126 entry IPv4 neighbor statiche** unicamente per i dispositivi sul medesimo dominio L2, usando i MAC esplicitamente dichiarati in lab.conf. Non sono nuove rotte: le rotte sono identiche al lab precedente.

Questa correzione mitiga una possibile causa dei timeout, ma non garantisce un risultato 620/620 quando il problema deriva dal carico sul Mac o dal processo checker.

## Avvio e verifica

Dalla cartella lab/:

```sh
kathara lstart --noterminals
kathara linfo
kathara exec pc4 -- ping -c 5 -W 2 10.11.4.12
kathara exec pc16 -- ping -c 5 -W 2 10.11.2.15
kathara exec pc19 -- ping -c 5 -W 2 10.11.2.12
kathara lclean
```

Esegui prima la **correction_baseline.yaml** della rete. La correction DNS ha senso solo dopo l'aggiunta del DNS da parte dell'agente LLM. Non modificare i test della correction per adattarli ai risultati.
