# T1 COST266 — Fase 6/6: Verifiche finali

**Obiettivo della fase:** Effettuare le verifiche statiche e il controllo di completezza del lavoro delle fasi 1–5, senza lanciare il benchmark dinamico.

## Contesto operativo e vincoli invarianti

Stai lavorando **sullo stesso laboratorio Kathara COST266 già esistente e predisposto**, composto da **37 router e 57 collegamenti punto-punto**. Questa è una fase di un intervento in **6 passaggi sequenziali** sul DNS, non un nuovo laboratorio.

- Conserva integralmente la topologia backbone, gli indirizzi IPv4, le loopback, le rotte statiche e i file `.startup` dei router; non aggiungere router, dispositivi, WAN, LAN, collision domain o interfacce.
- Preserva i file e le impostazioni già presenti. Aggiungi o aggiorna solo la configurazione DNS pertinente alla fase corrente, con file BIND9 persistenti nelle directory delle macchine DNS; nelle `.startup` delle sole macchine DNS interessate aggiungi, quando necessario e senza duplicati, `systemctl restart named` dopo la configurazione di rete. Non cambiare mai gli `.startup` dei router.
- I server autorevoli hanno `recursion no`; i resolver ricorsivi hanno `recursion yes` e non ospitano zone autorevoli, salvo i root hints. Usa `dnssec-validation no` per la gerarchia artificiale non firmata. Non usare DNS pubblici, forwarder esterni o root server Internet.
- Per ogni zona autorevole crea un SOA, NS all'apice e un record A valido per il suo nameserver. Per le zone non radice usa `ns1.<zona>.`, con il vero IP della macchina assegnata; per la radice usa `a.root-servers.` → `10.210.0.10`. Le deleghe NS nella zona padre devono essere coerenti con quelle della figlia e comprendere i glue A necessari.
- Una sola macchina può ospitare più zone indipendenti, ciascuna con il proprio SOA e NS. Non assegnare ruoli DNS ai router e non creare un host per ogni zona.
- Non introdurre i vecchi TLD `research.`, `services.`, `lab.`, né le sottozone cittadine `services`, `research`, `admin`.
- Se host, IP, LAN o percorsi di rete richiesti risultano assenti, **segnala la mancanza senza crearli o correggerli autonomamente**.
- Non anticipare le altre fasi e non rimuovere alcuna configurazione completata in precedenza. Esegui, se gli strumenti sono disponibili, `named-checkconf` e `named-checkzone` per i file della fase corrente; **non eseguire test dinamici Kathara o `dig`**, affidati al benchmark separato.

A regime, l'obiettivo complessivo resta **67 zone autorevoli e 66 deleghe DNS**: radice (1), TLD (3), paesi (22), città (37), sottozone funzionali (4). Alcune deleghe saranno temporaneamente incomplete fino alle fasi successive: non considerarlo un errore delle fasi intermedie.

## Configurazione richiesta in questa fase

Controlla il laboratorio nel suo complesso, preservando le configurazioni già generate. Completa solo eventuali correzioni strettamente DNS necessarie a soddisfare le specifiche, senza cambiare topologia o routing.

### Vincoli originali da ricontrollare

- Mantieni invariati tutti i 37 router e i 57 collegamenti del backbone COST266.
- Non modificare gli indirizzi IPv4, le loopback o le rotte statiche già configurate.
- Non modificare i file di startup dei router.
- Utilizza BIND9 sulle macchine assegnate ai ruoli DNS.
- Conserva la separazione tra server autorevoli, resolver ricorsivi e client.
- Non aggiungere dispositivi, LAN o interfacce durante questa fase di configurazione DNS.
- Preserva il contenuto esistente dei file del laboratorio e aggiungi esclusivamente le configurazioni DNS necessarie.
- Inserisci le configurazioni BIND9 persistenti nelle directory dei relativi dispositivi.
- Avvia il servizio DNS tramite `systemctl restart named`.
- Non configurare deleghe per i TLD `research.`, `services.` e `lab.`, né le sottozone cittadine `services`, `research` e `admin` appartenenti alla precedente gerarchia.
- Se gli host DNS, le LAN di accesso o gli indirizzi richiesti non risultano già predisposti nel laboratorio, segnala esplicitamente le mancanze senza alterare autonomamente la topologia.

### Verifiche richieste nel prompt originale

La configurazione prodotta deve permettere di verificare:

- La presenza di tutte le **67 zone autorevoli** e delle **66 deleghe**.
- La correttezza dei record SOA, NS e degli eventuali glue record.
- La coerenza tra deleghe dei domini-paese e zone cittadine.
- La presenza e la correttezza dei 37 record MX delle città e dei rispettivi record A.
- La corretta risoluzione dei record A e MX da entrambi i client attraverso i due resolver.
- La risoluzione dei domini funzionali `infra.` e `test.`.
- Il corretto comportamento delle risposte autoritative e ricorsive.
- La restituzione di `NXDOMAIN` per `missing.negative.test.`.
- La conservazione delle configurazioni di rete originali.

Verifica staticamente la sintassi delle configurazioni mediante `named-checkconf` e `named-checkzone`, quando disponibili. La validazione dinamica tramite Kathara e `dig` sarà eseguita separatamente dal sistema di benchmark.

**Obiettivo del benchmark (originale):** Verificare la capacità del modello di configurare una gerarchia DNS distribuita sulla rete europea COST266, rispettando le 67 zone e le 66 deleghe previste, garantendo la coerenza dei record SOA, NS, A e MX, il corretto funzionamento dei resolver ricorsivi e la conservazione del backbone originale.

Prepara un rapporto finale conciso con conteggi di zone/deleghe, configurazioni controllate, eventuali errori DNS corretti e impedimenti rimasti. Non dichiarare il successo dei test dinamici perché saranno eseguiti separatamente.

## Criterio di completamento della fase

Verifica statica completata (`named-checkconf`, `named-checkzone`, quando disponibili), inventario di **67 zone e 66 deleghe**, controllo dei **37 MX**, dei client/resolver e della preservazione del backbone originale. Le prove dinamiche con Kathara e `dig` restano a carico del sistema di benchmark.
