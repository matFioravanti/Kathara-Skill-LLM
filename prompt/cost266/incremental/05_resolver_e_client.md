# T1 COST266 — Fase 5/6: Resolver e client

**Obiettivo della fase:** Configurare due resolver ricorsivi e due client DNS affinché risolvano la gerarchia artificiale senza dipendere da Internet.

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

Questa fase non crea nuove zone autorevoli né deleghe. Preserva quelle realizzate nelle fasi 1–4.

- **Resolver ricorsivi:** Configura due local name server distinti:
  - `c266_resolver_1` → `10.210.34.10`
  - `c266_resolver_2` → `10.210.36.10`

- **Client DNS:** Configura i seguenti client:
  - `c266_client_1` → utilizza `10.210.34.10` come resolver.
  - `c266_client_2` → utilizza `10.210.36.10` come resolver.

- **Risoluzione ricorsiva:** Entrambi i resolver devono effettuare la risoluzione a partire dalla root artificiale `10.210.0.10`, seguendo le deleghe verso i TLD, i domini-paese e le zone cittadine oppure le sottozone funzionali.

- **Root hints:** Configura i file root hints affinché puntino esclusivamente alla root artificiale del laboratorio.

- **Separazione dei ruoli:** I resolver devono avere `recursion yes`, `allow-recursion { any; }` e non devono ospitare zone autorevoli, eccetto la zona di tipo `hint` per la radice.

- **Isolamento:** Disabilita la validazione DNSSEC per la gerarchia artificiale non firmata. Non utilizzare DNS pubblici, root server di Internet o forwarder esterni.

Il file di root hints su entrambi i resolver deve contenere esclusivamente `a.root-servers.` con indirizzo `10.210.0.10`. Nei client configura in modo persistente il corretto `nameserver` in `/etc/resolv.conf`, evitando risolutori pubblici o nameserver autorevoli. Mantieni separati i ruoli DNS di server autorevoli, resolver e client.

## Criterio di completamento della fase

I due resolver (`c266_resolver_1`, `c266_resolver_2`) devono avere ricorsione attiva, root hints locali e nessuna zona master/slave. Entrambi i client devono usare l'IP del resolver previsto. Rimangono **67 zone e 66 deleghe**.
