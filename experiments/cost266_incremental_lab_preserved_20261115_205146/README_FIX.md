# COST266 — baseline IPv4 statico riparato

Topologia originale: 37 router, 57 link WAN e 10 reti di accesso con 16 host.
Nessun link, nodo, indirizzo o next-hop e stato modificato.

## Correzione

Il checker riconosceva tutti i nodi e i domini, ma non trovava gli indirizzi IPv4 sulle interfacce dei router.
Ogni `.startup` router eseguiva subito tre comandi `sysctl` con `set -eu`: qualsiasi errore
(privi di binario, sysctl non scrivibile, restrizioni del container) interrompeva il resto
dello startup, prima di configurare loopback, WAN e reti di accesso.

Le tre opzioni sono ora impostate dal runtime Kathara in `lab.conf` tramite
`[sysctl]`, come previsto dalla documentazione ufficiale. Gli startup continuano
a configurare gli stessi IP e route mediante `ip -4`.

## Verifica su macchina con Kathara e Docker

Da dentro questa directory (`lab/`):

```sh
kathara lstart
kathara linfo
kathara exec r_amsterdam -- ip -o -4 addr show
kathara exec r_amsterdam -- cat /proc/sys/net/ipv4/ip_forward
kathara exec r_amsterdam -- ip -4 route show
kathara exec r_amsterdam -- ping -c 2 10.100.0.2
kathara exec c266_client_1 -- ping -c 2 10.210.0.10
```

Se un controllo non passa, ispezionare prima lo startup log del router.
Ripetere il checker usando le correction originali: non sono incluse in questo archivio.
`lab_result.xlsx` era un risultato precedente (correction 4) ed e stato escluso per non creare ambiguita.

Le 16 macchine `c266_*` sono lasciate nella loro configurazione DNS di base, senza
introdurre zone, deleghe o demoni non richiesti nei test infrastrutturali.

**Limite**: audit statico superato; il checker Docker/Kathara non puo essere
rieseguito in questo ambiente, quindi i punteggi dopo la correzione non sono
ancora confermati.
