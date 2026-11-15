# T1 COST266 — Fase 3/6: Zone cittadine

**Obiettivo della fase:** Creare le 37 zone autorevoli cittadine e tutti i record A/MX previsti, usando esclusivamente le loopback dei router COST266.

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

Tutte le **37 zone cittadine** già delegate dalle rispettive zone-paese devono essere gestite da `c266_cities` (`10.210.28.10`), senza creare altri host e senza eseguire BIND9 sui router. Per ciascuna zona usa SOA proprio, NS `ns1.<città>.<paese>.europa.` e record A per tale NS pari a `10.210.28.10`.

La corrispondenza tra FQDN cittadino e paese è la stessa già specificata nella fase 2. Per rendere questa fase autosufficiente, riporto tutte le associazioni:

Ciascun dominio-paese deve delegare le città corrispondenti ai router geografici COST266, secondo le seguenti associazioni:

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

### Record cittadini e indirizzi

Configura all'interno di ciascuna delle 37 zone cittadine i record necessari per identificare il relativo router COST266 e simulare i riferimenti DNS dei servizi web e di posta elettronica.

- **Record A:** Per ogni zona cittadina configura:
  - Un record A all'apice della zona, associato all'indirizzo IPv4 di loopback del router corrispondente.
  - Un record `www.<città>.<paese>.europa.` associato allo stesso indirizzo.
  - Un record `mail.<città>.<paese>.europa.` associato allo stesso indirizzo.

- **Record MX:** Per ogni zona cittadina configura un record MX con priorità 10, diretto a `mail.<città>.<paese>.europa.`.

- **Indirizzamento:** Utilizza esclusivamente gli indirizzi IPv4 di loopback già configurati sui router COST266, con le seguenti associazioni:

  - Amsterdam → `10.200.0.1`
  - Athens → `10.200.0.2`
  - Barcelona → `10.200.0.3`
  - Belgrade → `10.200.0.4`
  - Berlin → `10.200.0.5`
  - Birmingham → `10.200.0.6`
  - Bordeaux → `10.200.0.7`
  - Brussels → `10.200.0.8`
  - Budapest → `10.200.0.9`
  - Copenhagen → `10.200.0.10`
  - Dublin → `10.200.0.11`
  - Dusseldorf → `10.200.0.12`
  - Frankfurt → `10.200.0.13`
  - Glasgow → `10.200.0.14`
  - Hamburg → `10.200.0.15`
  - Helsinki → `10.200.0.16`
  - Krakow → `10.200.0.17`
  - Lisbon → `10.200.0.18`
  - London → `10.200.0.19`
  - Lyon → `10.200.0.20`
  - Madrid → `10.200.0.21`
  - Marseille → `10.200.0.22`
  - Milan → `10.200.0.23`
  - Munich → `10.200.0.24`
  - Oslo → `10.200.0.25`
  - Palermo → `10.200.0.26`
  - Paris → `10.200.0.27`
  - Prague → `10.200.0.28`
  - Rome → `10.200.0.29`
  - Seville → `10.200.0.30`
  - Sofia → `10.200.0.31`
  - Stockholm → `10.200.0.32`
  - Strasbourg → `10.200.0.33`
  - Vienna → `10.200.0.34`
  - Warsaw → `10.200.0.35`
  - Zagreb → `10.200.0.36`
  - Zurich → `10.200.0.37`

Ad esempio, per la zona `rome.it.europa.` devono essere presenti:

- `rome.it.europa. IN A 10.200.0.29`
- `www.rome.it.europa. IN A 10.200.0.29`
- `mail.rome.it.europa. IN A 10.200.0.29`
- `rome.it.europa. IN MX 10 mail.rome.it.europa.`

I record `www` e `mail` rappresentano riferimenti DNS da verificare. Non è richiesta l'installazione di server HTTP o SMTP sui router.

Controlla che il nameserver della zona figlia sia lo stesso indicato nella delega della zona-paese e che i glue nella zona padre puntino a `10.210.28.10`.

## Criterio di completamento della fase

Devono risultare **37 zone cittadine indipendenti** e per ciascuna: SOA, NS, A dell'NS, A all'apice, A `www`, A `mail` e MX con priorità 10. Totale progressivo **63 zone** (1+3+22+37); tutte le 37 deleghe cittadine sono già nella fase 2.
