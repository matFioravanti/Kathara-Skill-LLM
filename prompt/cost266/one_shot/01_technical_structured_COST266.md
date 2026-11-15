# T1 — COST266: Configurazione DNS europea semplificata

Genera la configurazione DNS per il laboratorio Kathara esistente basato sulla topologia europea COST266, composta da 37 router e 57 collegamenti punto-punto, mantenendo invariati la topologia backbone, gli indirizzi IP e le rotte statiche già configurate.

Il laboratorio deve essere predisposto con gli host DNS e le LAN di accesso indicati nelle specifiche. Non introdurre nuovi router, collegamenti WAN o modifiche al piano di indirizzamento esistente.

- **Gerarchia:** Configura una gerarchia DNS artificiale composta complessivamente da **67 zone autorevoli e 66 deleghe DNS**, organizzate nel seguente modo:
  - 1 dominio radice `.`
  - 3 TLD artificiali: `europa.`, `infra.`, `test.`
  - 22 domini-paese appartenenti a `europa.`
  - 37 domini-città appartenenti ai rispettivi paesi
  - 4 sottozone funzionali appartenenti a `infra.` e `test.`

## 1. Gerarchia DNS europea

- **Dominio radice:** Configura il dominio `.` come radice artificiale dell'intera gerarchia DNS. La radice deve delegare i tre TLD `europa.`, `infra.` e `test.` ai rispettivi name server autorevoli.

- **TLD europa:** Configura `europa.` come dominio principale della gerarchia geografica. Deve delegare i seguenti 22 domini-paese ai rispettivi name server autorevoli:

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

## 2. Gerarchia DNS funzionale

- **TLD infra:** Configura `infra.` con le seguenti due sottozone delegate:
  - `dns.infra.` — Informazioni sui server DNS della rete
  - `routing.infra.` — Informazioni relative ai router del backbone

- **TLD test:** Configura `test.` con le seguenti due sottozone delegate:
  - `positive.test.` — Verifica della corretta risoluzione DNS
  - `negative.test.` — Verifica delle risposte negative DNS

Le quattro sottozone devono essere autorevoli e indipendenti, con record SOA, NS e glue record ove necessari.

## 3. Corrispondenza tra zone DNS e macchine

Utilizza le seguenti associazioni tra zone e host del laboratorio predisposto:

- **Dominio radice:** `.` → `c266_root`, IP `10.210.0.10`
- **TLD europa:** `europa.` → `c266_tld_europa`, IP `10.210.0.11`
- **TLD infra:** `infra.` → `c266_tld_infra`, IP `10.210.12.11`
- **TLD test:** `test.` → `c266_tld_test`, IP `10.210.18.11`
- **Domini-paese:** tutte le 22 zone sotto `europa.` → `c266_countries`, IP `10.210.12.10`
- **Domini-città:** tutte le 37 zone cittadine → `c266_cities`, IP `10.210.28.10`
- **Sottozone funzionali:** `dns.infra.`, `routing.infra.`, `positive.test.` e `negative.test.` → `c266_functional_1`, IP `10.210.18.10`

Ogni server autorevole deve gestire tutte le zone assegnate tramite BIND9. Le zone condivise devono restare logicamente distinte e avere ciascuna il proprio SOA e i propri record NS.

Non assegnare ruoli DNS ai 37 router e non creare una macchina distinta per ogni zona o città.

## 4. Deleghe e record autorevoli

- **Deleghe DNS:** Configura le 66 deleghe richieste, con record NS coerenti tra zona padre e zona figlia.
- **Glue record:** Inserisci i record A di glue necessari per tutti i name server interni alle rispettive zone delegate. Utilizza gli indirizzi IP reali degli host autorevoli.
- **SOA:** Configura un record SOA valido per ciascuna delle 67 zone.
- **NS:** Utilizza `ns1.<zona>.` come nome del name server autorevole per ciascuna zona non radice, con un record A associato all'indirizzo IP dell'host che la gestisce.
- **Root:** Utilizza `a.root-servers.` come name server della radice artificiale, associato a `10.210.0.10`.
- **Autorevolezza:** Disabilita la ricorsione su tutti i server DNS autorevoli (`recursion no`) e abilita le risposte alle query provenienti dalla rete del laboratorio.

## 5. Record DNS delle città

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

## 6. Record DNS funzionali

Configura i seguenti record A nelle rispettive zone autorevoli:

- `root.dns.infra.` → `10.210.0.10`
- `resolvers.dns.infra.` → `10.210.34.10`
- `backbone.routing.infra.` → `10.200.0.13`
- `www.positive.test.` → `10.210.18.10`

Configura la zona `negative.test.` in modo che sia autorevole e permetta di verificare correttamente la risposta `NXDOMAIN` alla query `missing.negative.test.`. Non inserire un record corrispondente a tale nome.

## 7. Risoluzione locale

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

## 8. Vincoli di configurazione

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

## 9. Verifiche richieste

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

**Obiettivo del benchmark:** Verificare la capacità del modello di configurare una gerarchia DNS distribuita sulla rete europea COST266, rispettando le 67 zone e le 66 deleghe previste, garantendo la coerenza dei record SOA, NS, A e MX, il corretto funzionamento dei resolver ricorsivi e la conservazione del backbone originale.