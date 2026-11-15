# T1 COST266 — Fase 1/6: Root e TLD

**Obiettivo della fase:** Configurare la root artificiale e i tre TLD, senza ancora creare le zone-paese, le città o le sottozone funzionali.

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

Configura la **radice artificiale `.`** su `c266_root` (`10.210.0.10`). Il suo name server deve essere `a.root-servers.` con record A `10.210.0.10`. Nella root configura le deleghe verso i tre TLD:

- `europa.` → `ns1.europa.` → `10.210.0.11`
- `infra.` → `ns1.infra.` → `10.210.12.11`
- `test.` → `ns1.test.` → `10.210.18.11`

Predisponi le **tre zone TLD autorevoli** con SOA, NS e record A `ns1` su queste macchine:

| Zona | Host | IP autorevole |
|---|---|---|
| `europa.` | `c266_tld_europa` | `10.210.0.11` |
| `infra.` | `c266_tld_infra` | `10.210.12.11` |
| `test.` | `c266_tld_test` | `10.210.18.11` |

Le future deleghe da `europa.` ai 22 paesi e da `infra.`/`test.` alle quattro sottozone saranno aggiunte nelle fasi 2 e 4. Non inventare record di host o zone non richiesti.

## Criterio di completamento della fase

Devono risultare **4 zone autorevoli** (`.`, `europa.`, `infra.`, `test.`) e **3 deleghe** dalla root. I quattro server devono esporre BIND9 autorevole senza ricorsione.
