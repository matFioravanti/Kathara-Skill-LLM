# T1 COST266 — Fase 4/6: Zone funzionali

**Obiettivo della fase:** Creare le quattro sottozone di infra. e test. e i relativi record funzionali e di verifica negativa.

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

Le zone TLD `infra.` e `test.` sono già ospitate dagli host predisposti nella fase 1. Aggiungi in tali TLD le quattro deleghe e i glue necessari. Gestisci **tutte le quattro nuove zone** su `c266_functional_1` (`10.210.18.10`), con SOA, NS e A `ns1` propri per ciascuna zona.

### Struttura richiesta

- **TLD infra:** Configura `infra.` con le seguenti due sottozone delegate:
  - `dns.infra.` — Informazioni sui server DNS della rete
  - `routing.infra.` — Informazioni relative ai router del backbone

- **TLD test:** Configura `test.` con le seguenti due sottozone delegate:
  - `positive.test.` — Verifica della corretta risoluzione DNS
  - `negative.test.` — Verifica delle risposte negative DNS

Le quattro sottozone devono essere autorevoli e indipendenti, con record SOA, NS e glue record ove necessari.

### Record richiesti

Configura i seguenti record A nelle rispettive zone autorevoli:

- `root.dns.infra.` → `10.210.0.10`
- `resolvers.dns.infra.` → `10.210.34.10`
- `backbone.routing.infra.` → `10.200.0.13`
- `www.positive.test.` → `10.210.18.10`

Configura la zona `negative.test.` in modo che sia autorevole e permetta di verificare correttamente la risposta `NXDOMAIN` alla query `missing.negative.test.`. Non inserire un record corrispondente a tale nome.

Per `negative.test.` NON aggiungere il nome `missing.negative.test.`; deve poter produrre NXDOMAIN come zona autorevole.

## Criterio di completamento della fase

Le nuove zone sono **`dns.infra.`, `routing.infra.`, `positive.test.`, `negative.test.`** e le nuove deleghe sono **4**. Al termine sono presenti tutte le **67 zone e 66 deleghe** del progetto.
