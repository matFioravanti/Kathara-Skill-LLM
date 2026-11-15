# T1 COST266 — Fase 2/6: Paesi e deleghe

**Obiettivo della fase:** Creare 22 zone-paese autorevoli e le deleghe coerenti dal TLD europeo, predisponendo anche le deleghe alle 37 città senza creare ancora le loro zone.

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

Usa `c266_countries` (`10.210.12.10`) come **unico host autorevole per tutte le 22 zone-paese** sotto `europa.`. Ciascuna zona-paese deve avere SOA e NS propri: `ns1.<paese>.europa.` con A `10.210.12.10`.

Su `c266_tld_europa` aggiorna `europa.` affinché deleghi correttamente i 22 paesi con NS e glue A necessari. Nelle zone-paese delega le 37 zone cittadine indicate qui sotto, usando come NS di ciascuna `ns1.<città>.<paese>.europa.` con glue A `10.210.28.10`, IP dell'host `c266_cities`. **Le zone cittadine stesse saranno create nella fase 3.**

- **TLD europa:**Configura `europa.` come dominio principale della gerarchia geografica. Deve delegare i seguenti 22 domini-paese ai rispettivi name server autorevoli:

  - `at.europa.` — Austria
  - `be.europa.` — Belgio
  - `bg.europa.` — Bulgaria
  - `ch.europa.` — Svizzera
  - `cz.europa.` — Repubblica Ceca
  - `de.europa.` — Germania
  - `dk.europa.` — Danimarca
  - `es.europa.` — Spagna
  - `fi.europa.` — Finlandia
  - `fr.europa.` — Francia
  - `gr.europa.` — Grecia
  - `hr.europa.` — Croazia
  - `hu.europa.` — Ungheria
  - `ie.europa.` — Irlanda
  - `it.europa.` — Italia
  - `nl.europa.` — Paesi Bassi
  - `no.europa.` — Norvegia
  - `pl.europa.` — Polonia
  - `pt.europa.` — Portogallo
  - `rs.europa.` — Serbia
  - `se.europa.` — Svezia
  - `uk.europa.` — Regno Unito

- **Domini-città:** Ciascun dominio-paese deve delegare le città corrispondenti ai router geografici COST266, secondo le seguenti associazioni:

  - `at.europa.` → `vienna.at.europa.`
  - `be.europa.` → `brussels.be.europa.`
  - `bg.europa.` → `sofia.bg.europa.`
  - `ch.europa.` → `zurich.ch.europa.`
  - `cz.europa.` → `prague.cz.europa.`
  - `de.europa.` → `berlin.de.europa.`, `dusseldorf.de.europa.`, `frankfurt.de.europa.`, `hamburg.de.europa.`, `munich.de.europa.`
  - `dk.europa.` → `copenhagen.dk.europa.`
  - `es.europa.` → `barcelona.es.europa.`, `madrid.es.europa.`, `seville.es.europa.`
  - `fi.europa.` → `helsinki.fi.europa.`
  - `fr.europa.` → `bordeaux.fr.europa.`, `lyon.fr.europa.`, `marseille.fr.europa.`, `paris.fr.europa.`, `strasbourg.fr.europa.`
  - `gr.europa.` → `athens.gr.europa.`
  - `hr.europa.` → `zagreb.hr.europa.`
  - `hu.europa.` → `budapest.hu.europa.`
  - `ie.europa.` → `dublin.ie.europa.`
  - `it.europa.` → `milan.it.europa.`, `palermo.it.europa.`, `rome.it.europa.`
  - `nl.europa.` → `amsterdam.nl.europa.`
  - `no.europa.` → `oslo.no.europa.`
  - `pl.europa.` → `krakow.pl.europa.`, `warsaw.pl.europa.`
  - `pt.europa.` → `lisbon.pt.europa.`
  - `rs.europa.` → `belgrade.rs.europa.`
  - `se.europa.` → `stockholm.se.europa.`
  - `uk.europa.` → `birmingham.uk.europa.`, `glasgow.uk.europa.`, `london.uk.europa.`

Ogni città deve costituire una zona DNS autorevole distinta, direttamente delegata dal relativo dominio-paese. Non creare ulteriori sottozone delegate al di sotto delle città.

Non aggiungere altri livelli sotto le città e non creare nuovi dispositivi DNS.

## Criterio di completamento della fase

Devono risultare **22 nuove zone-paese**, portando il totale progressivo a **26 zone**, più **22 deleghe TLD→paesi** e **37 deleghe paesi→città**. Il totale delle deleghe predisposte dopo questa fase è **62** (3+22+37); le quattro deleghe funzionali saranno aggiunte nella fase 4.
