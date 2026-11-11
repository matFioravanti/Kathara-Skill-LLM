# COST266 — Gerarchia DNS europea multi-TLD (proposta v2)

> **Stato:** specifica logica di progetto, **non** configurazione BIND9 già installata. La rete fisica originale resta di 37 router e 57 collegamenti. Nessun indirizzo IP per i server DNS è stato inventato.

## 1. Scopo e differenze rispetto all’albero precedente

Questo progetto estende gli alberi originali COST266. Invece di un unico TLD `test.` contenente `europa.test.`, propone **sei TLD artificiali direttamente delegati dalla radice `.`**: `europa.`, `infra.`, `research.`, `services.`, `lab.` e `test.`. I 37 nodi del JSON diventano 37 città sotto `europa.` e 22 domini-paese. Gli altri cinque TLD rappresentano servizi o scenari di benchmark e non duplicano le città.

**Incompatibilità nominale da considerare:** per esempio `rome.it.europa.test.` (v1) diventerebbe `rome.it.europa.` (v2). È una **nuova specifica**, da applicare solo in un successivo laboratorio DNS; non modifica l’attuale archivio Kathará. Le sigle nazionali sono etichette DNS simulate **sotto `europa.`**, non veri ccTLD delegati dalla radice pubblica.

## 2. Dimensioni del progetto

| Categoria | Quantità |
|---|---:|
| Radice artificiale `.` | 1 |
| TLD artificiali | 6 |
| Domini-paese sotto `europa.` | 22 |
| Zone cittadine (una per nodo COST266) | 37 |
| Sottozone delegate per città (`services`, `research`, `admin`) | 111 |
| Altre zone funzionali distribuite sui cinque TLD | 24 |
| **Zone DNS complessive** | **201** |
| **Deleghe parent → child previste** | **200** |

**Nota:** il numero di zone e deleghe descrive la gerarchia DNS, non il numero di container. Un server autorizzato a svolgere più ruoli, se previsto esplicitamente nella futura specifica di deployment, può ospitare diverse zone; in assenza di tale scelta la Skill DNS privilegia host distinti per ruolo.

## 3. Albero completo di tutte le 201 zone

Le voci sotto l’albero sono **zone autoritative distinte**: il genitore pubblica una delega `NS` per ogni figlia. SOA, NS di apex e record A per gli eventuali nameserver sono parte della configurazione di ciascuna zona. I nomi sono FQDN con punto finale.

```text
.   [radice DNS artificiale]
├── europa.   [TLD artificiale]
│   ├── at.europa.   [Austria]
│   │   └── vienna.at.europa.   [città COST266]
│   │       ├── admin.vienna.at.europa.   [sottozona delegata]
│   │       ├── research.vienna.at.europa.   [sottozona delegata]
│   │       └── services.vienna.at.europa.   [sottozona delegata]
│   ├── be.europa.   [Belgio]
│   │   └── brussels.be.europa.   [città COST266]
│   │       ├── admin.brussels.be.europa.   [sottozona delegata]
│   │       ├── research.brussels.be.europa.   [sottozona delegata]
│   │       └── services.brussels.be.europa.   [sottozona delegata]
│   ├── bg.europa.   [Bulgaria]
│   │   └── sofia.bg.europa.   [città COST266]
│   │       ├── admin.sofia.bg.europa.   [sottozona delegata]
│   │       ├── research.sofia.bg.europa.   [sottozona delegata]
│   │       └── services.sofia.bg.europa.   [sottozona delegata]
│   ├── ch.europa.   [Svizzera]
│   │   └── zurich.ch.europa.   [città COST266]
│   │       ├── admin.zurich.ch.europa.   [sottozona delegata]
│   │       ├── research.zurich.ch.europa.   [sottozona delegata]
│   │       └── services.zurich.ch.europa.   [sottozona delegata]
│   ├── cz.europa.   [Repubblica Ceca]
│   │   └── prague.cz.europa.   [città COST266]
│   │       ├── admin.prague.cz.europa.   [sottozona delegata]
│   │       ├── research.prague.cz.europa.   [sottozona delegata]
│   │       └── services.prague.cz.europa.   [sottozona delegata]
│   ├── de.europa.   [Germania]
│   │   ├── berlin.de.europa.   [città COST266]
│   │   │   ├── admin.berlin.de.europa.   [sottozona delegata]
│   │   │   ├── research.berlin.de.europa.   [sottozona delegata]
│   │   │   └── services.berlin.de.europa.   [sottozona delegata]
│   │   ├── dusseldorf.de.europa.   [città COST266]
│   │   │   ├── admin.dusseldorf.de.europa.   [sottozona delegata]
│   │   │   ├── research.dusseldorf.de.europa.   [sottozona delegata]
│   │   │   └── services.dusseldorf.de.europa.   [sottozona delegata]
│   │   ├── frankfurt.de.europa.   [città COST266]
│   │   │   ├── admin.frankfurt.de.europa.   [sottozona delegata]
│   │   │   ├── research.frankfurt.de.europa.   [sottozona delegata]
│   │   │   └── services.frankfurt.de.europa.   [sottozona delegata]
│   │   ├── hamburg.de.europa.   [città COST266]
│   │   │   ├── admin.hamburg.de.europa.   [sottozona delegata]
│   │   │   ├── research.hamburg.de.europa.   [sottozona delegata]
│   │   │   └── services.hamburg.de.europa.   [sottozona delegata]
│   │   └── munich.de.europa.   [città COST266]
│   │       ├── admin.munich.de.europa.   [sottozona delegata]
│   │       ├── research.munich.de.europa.   [sottozona delegata]
│   │       └── services.munich.de.europa.   [sottozona delegata]
│   ├── dk.europa.   [Danimarca]
│   │   └── copenhagen.dk.europa.   [città COST266]
│   │       ├── admin.copenhagen.dk.europa.   [sottozona delegata]
│   │       ├── research.copenhagen.dk.europa.   [sottozona delegata]
│   │       └── services.copenhagen.dk.europa.   [sottozona delegata]
│   ├── es.europa.   [Spagna]
│   │   ├── barcelona.es.europa.   [città COST266]
│   │   │   ├── admin.barcelona.es.europa.   [sottozona delegata]
│   │   │   ├── research.barcelona.es.europa.   [sottozona delegata]
│   │   │   └── services.barcelona.es.europa.   [sottozona delegata]
│   │   ├── madrid.es.europa.   [città COST266]
│   │   │   ├── admin.madrid.es.europa.   [sottozona delegata]
│   │   │   ├── research.madrid.es.europa.   [sottozona delegata]
│   │   │   └── services.madrid.es.europa.   [sottozona delegata]
│   │   └── seville.es.europa.   [città COST266]
│   │       ├── admin.seville.es.europa.   [sottozona delegata]
│   │       ├── research.seville.es.europa.   [sottozona delegata]
│   │       └── services.seville.es.europa.   [sottozona delegata]
│   ├── fi.europa.   [Finlandia]
│   │   └── helsinki.fi.europa.   [città COST266]
│   │       ├── admin.helsinki.fi.europa.   [sottozona delegata]
│   │       ├── research.helsinki.fi.europa.   [sottozona delegata]
│   │       └── services.helsinki.fi.europa.   [sottozona delegata]
│   ├── fr.europa.   [Francia]
│   │   ├── bordeaux.fr.europa.   [città COST266]
│   │   │   ├── admin.bordeaux.fr.europa.   [sottozona delegata]
│   │   │   ├── research.bordeaux.fr.europa.   [sottozona delegata]
│   │   │   └── services.bordeaux.fr.europa.   [sottozona delegata]
│   │   ├── lyon.fr.europa.   [città COST266]
│   │   │   ├── admin.lyon.fr.europa.   [sottozona delegata]
│   │   │   ├── research.lyon.fr.europa.   [sottozona delegata]
│   │   │   └── services.lyon.fr.europa.   [sottozona delegata]
│   │   ├── marseille.fr.europa.   [città COST266]
│   │   │   ├── admin.marseille.fr.europa.   [sottozona delegata]
│   │   │   ├── research.marseille.fr.europa.   [sottozona delegata]
│   │   │   └── services.marseille.fr.europa.   [sottozona delegata]
│   │   ├── paris.fr.europa.   [città COST266]
│   │   │   ├── admin.paris.fr.europa.   [sottozona delegata]
│   │   │   ├── research.paris.fr.europa.   [sottozona delegata]
│   │   │   └── services.paris.fr.europa.   [sottozona delegata]
│   │   └── strasbourg.fr.europa.   [città COST266]
│   │       ├── admin.strasbourg.fr.europa.   [sottozona delegata]
│   │       ├── research.strasbourg.fr.europa.   [sottozona delegata]
│   │       └── services.strasbourg.fr.europa.   [sottozona delegata]
│   ├── gr.europa.   [Grecia]
│   │   └── athens.gr.europa.   [città COST266]
│   │       ├── admin.athens.gr.europa.   [sottozona delegata]
│   │       ├── research.athens.gr.europa.   [sottozona delegata]
│   │       └── services.athens.gr.europa.   [sottozona delegata]
│   ├── hr.europa.   [Croazia]
│   │   └── zagreb.hr.europa.   [città COST266]
│   │       ├── admin.zagreb.hr.europa.   [sottozona delegata]
│   │       ├── research.zagreb.hr.europa.   [sottozona delegata]
│   │       └── services.zagreb.hr.europa.   [sottozona delegata]
│   ├── hu.europa.   [Ungheria]
│   │   └── budapest.hu.europa.   [città COST266]
│   │       ├── admin.budapest.hu.europa.   [sottozona delegata]
│   │       ├── research.budapest.hu.europa.   [sottozona delegata]
│   │       └── services.budapest.hu.europa.   [sottozona delegata]
│   ├── ie.europa.   [Irlanda]
│   │   └── dublin.ie.europa.   [città COST266]
│   │       ├── admin.dublin.ie.europa.   [sottozona delegata]
│   │       ├── research.dublin.ie.europa.   [sottozona delegata]
│   │       └── services.dublin.ie.europa.   [sottozona delegata]
│   ├── it.europa.   [Italia]
│   │   ├── milan.it.europa.   [città COST266]
│   │   │   ├── admin.milan.it.europa.   [sottozona delegata]
│   │   │   ├── research.milan.it.europa.   [sottozona delegata]
│   │   │   └── services.milan.it.europa.   [sottozona delegata]
│   │   ├── palermo.it.europa.   [città COST266]
│   │   │   ├── admin.palermo.it.europa.   [sottozona delegata]
│   │   │   ├── research.palermo.it.europa.   [sottozona delegata]
│   │   │   └── services.palermo.it.europa.   [sottozona delegata]
│   │   └── rome.it.europa.   [città COST266]
│   │       ├── admin.rome.it.europa.   [sottozona delegata]
│   │       ├── research.rome.it.europa.   [sottozona delegata]
│   │       └── services.rome.it.europa.   [sottozona delegata]
│   ├── nl.europa.   [Paesi Bassi]
│   │   └── amsterdam.nl.europa.   [città COST266]
│   │       ├── admin.amsterdam.nl.europa.   [sottozona delegata]
│   │       ├── research.amsterdam.nl.europa.   [sottozona delegata]
│   │       └── services.amsterdam.nl.europa.   [sottozona delegata]
│   ├── no.europa.   [Norvegia]
│   │   └── oslo.no.europa.   [città COST266]
│   │       ├── admin.oslo.no.europa.   [sottozona delegata]
│   │       ├── research.oslo.no.europa.   [sottozona delegata]
│   │       └── services.oslo.no.europa.   [sottozona delegata]
│   ├── pl.europa.   [Polonia]
│   │   ├── krakow.pl.europa.   [città COST266]
│   │   │   ├── admin.krakow.pl.europa.   [sottozona delegata]
│   │   │   ├── research.krakow.pl.europa.   [sottozona delegata]
│   │   │   └── services.krakow.pl.europa.   [sottozona delegata]
│   │   └── warsaw.pl.europa.   [città COST266]
│   │       ├── admin.warsaw.pl.europa.   [sottozona delegata]
│   │       ├── research.warsaw.pl.europa.   [sottozona delegata]
│   │       └── services.warsaw.pl.europa.   [sottozona delegata]
│   ├── pt.europa.   [Portogallo]
│   │   └── lisbon.pt.europa.   [città COST266]
│   │       ├── admin.lisbon.pt.europa.   [sottozona delegata]
│   │       ├── research.lisbon.pt.europa.   [sottozona delegata]
│   │       └── services.lisbon.pt.europa.   [sottozona delegata]
│   ├── rs.europa.   [Serbia]
│   │   └── belgrade.rs.europa.   [città COST266]
│   │       ├── admin.belgrade.rs.europa.   [sottozona delegata]
│   │       ├── research.belgrade.rs.europa.   [sottozona delegata]
│   │       └── services.belgrade.rs.europa.   [sottozona delegata]
│   ├── se.europa.   [Svezia]
│   │   └── stockholm.se.europa.   [città COST266]
│   │       ├── admin.stockholm.se.europa.   [sottozona delegata]
│   │       ├── research.stockholm.se.europa.   [sottozona delegata]
│   │       └── services.stockholm.se.europa.   [sottozona delegata]
│   └── uk.europa.   [Regno Unito]
│       ├── birmingham.uk.europa.   [città COST266]
│       │   ├── admin.birmingham.uk.europa.   [sottozona delegata]
│       │   ├── research.birmingham.uk.europa.   [sottozona delegata]
│       │   └── services.birmingham.uk.europa.   [sottozona delegata]
│       ├── glasgow.uk.europa.   [città COST266]
│       │   ├── admin.glasgow.uk.europa.   [sottozona delegata]
│       │   ├── research.glasgow.uk.europa.   [sottozona delegata]
│       │   └── services.glasgow.uk.europa.   [sottozona delegata]
│       └── london.uk.europa.   [città COST266]
│           ├── admin.london.uk.europa.   [sottozona delegata]
│           ├── research.london.uk.europa.   [sottozona delegata]
│           └── services.london.uk.europa.   [sottozona delegata]
├── infra.   [TLD artificiale]
│   ├── dns.infra.   [sottozona funzionale]
│   │   ├── resolvers.dns.infra.   [sottozona funzionale]
│   │   ├── root.dns.infra.   [sottozona funzionale]
│   │   └── tld.dns.infra.   [sottozona funzionale]
│   ├── monitoring.infra.   [sottozona funzionale]
│   └── routing.infra.   [sottozona funzionale]
├── research.   [TLD artificiale]
│   ├── datasets.research.   [sottozona funzionale]
│   ├── experiments.research.   [sottozona funzionale]
│   │   ├── failures.experiments.research.   [sottozona funzionale]
│   │   └── latency.experiments.research.   [sottozona funzionale]
│   └── universities.research.   [sottozona funzionale]
├── services.   [TLD artificiale]
│   ├── api.services.   [sottozona funzionale]
│   ├── mail.services.   [sottozona funzionale]
│   └── web.services.   [sottozona funzionale]
│       └── portals.web.services.   [sottozona funzionale]
├── lab.   [TLD artificiale]
│   ├── benchmark.lab.   [sottozona funzionale]
│   │   └── scenarios.benchmark.lab.   [sottozona funzionale]
│   ├── checker.lab.   [sottozona funzionale]
│   └── clients.lab.   [sottozona funzionale]
└── test.   [TLD artificiale]
    ├── dnssec.test.   [sottozona funzionale]
    ├── negative.test.   [sottozona funzionale]
    │   ├── delegation.negative.test.   [sottozona funzionale]
    │   └── nxdomain.negative.test.   [sottozona funzionale]
    └── positive.test.   [sottozona funzionale]
```

## 4. Tutte le città e i rispettivi router COST266

| Paese / dominio-paese | Città / zona DNS | Router della rete |
|---|---|---|
| Austria (`at.europa.`) | Vienna — `vienna.at.europa.` | `r_vienna` |
| Belgio (`be.europa.`) | Brussels — `brussels.be.europa.` | `r_brussels` |
| Bulgaria (`bg.europa.`) | Sofia — `sofia.bg.europa.` | `r_sofia` |
| Svizzera (`ch.europa.`) | Zurich — `zurich.ch.europa.` | `r_zurich` |
| Repubblica Ceca (`cz.europa.`) | Prague — `prague.cz.europa.` | `r_prague` |
| Germania (`de.europa.`) | Berlin — `berlin.de.europa.` | `r_berlin` |
| Germania (`de.europa.`) | Dusseldorf — `dusseldorf.de.europa.` | `r_dusseldorf` |
| Germania (`de.europa.`) | Frankfurt — `frankfurt.de.europa.` | `r_frankfurt` |
| Germania (`de.europa.`) | Hamburg — `hamburg.de.europa.` | `r_hamburg` |
| Germania (`de.europa.`) | Munich — `munich.de.europa.` | `r_munich` |
| Danimarca (`dk.europa.`) | Copenhagen — `copenhagen.dk.europa.` | `r_copenhagen` |
| Spagna (`es.europa.`) | Barcelona — `barcelona.es.europa.` | `r_barcelona` |
| Spagna (`es.europa.`) | Madrid — `madrid.es.europa.` | `r_madrid` |
| Spagna (`es.europa.`) | Seville — `seville.es.europa.` | `r_seville` |
| Finlandia (`fi.europa.`) | Helsinki — `helsinki.fi.europa.` | `r_helsinki` |
| Francia (`fr.europa.`) | Bordeaux — `bordeaux.fr.europa.` | `r_bordeaux` |
| Francia (`fr.europa.`) | Lyon — `lyon.fr.europa.` | `r_lyon` |
| Francia (`fr.europa.`) | Marseille — `marseille.fr.europa.` | `r_marseille` |
| Francia (`fr.europa.`) | Paris — `paris.fr.europa.` | `r_paris` |
| Francia (`fr.europa.`) | Strasbourg — `strasbourg.fr.europa.` | `r_strasbourg` |
| Grecia (`gr.europa.`) | Athens — `athens.gr.europa.` | `r_athens` |
| Croazia (`hr.europa.`) | Zagreb — `zagreb.hr.europa.` | `r_zagreb` |
| Ungheria (`hu.europa.`) | Budapest — `budapest.hu.europa.` | `r_budapest` |
| Irlanda (`ie.europa.`) | Dublin — `dublin.ie.europa.` | `r_dublin` |
| Italia (`it.europa.`) | Milan — `milan.it.europa.` | `r_milan` |
| Italia (`it.europa.`) | Palermo — `palermo.it.europa.` | `r_palermo` |
| Italia (`it.europa.`) | Rome — `rome.it.europa.` | `r_rome` |
| Paesi Bassi (`nl.europa.`) | Amsterdam — `amsterdam.nl.europa.` | `r_amsterdam` |
| Norvegia (`no.europa.`) | Oslo — `oslo.no.europa.` | `r_oslo` |
| Polonia (`pl.europa.`) | Krakow — `krakow.pl.europa.` | `r_krakow` |
| Polonia (`pl.europa.`) | Warsaw — `warsaw.pl.europa.` | `r_warsaw` |
| Portogallo (`pt.europa.`) | Lisbon — `lisbon.pt.europa.` | `r_lisbon` |
| Serbia (`rs.europa.`) | Belgrade — `belgrade.rs.europa.` | `r_belgrade` |
| Svezia (`se.europa.`) | Stockholm — `stockholm.se.europa.` | `r_stockholm` |
| Regno Unito (`uk.europa.`) | Birmingham — `birmingham.uk.europa.` | `r_birmingham` |
| Regno Unito (`uk.europa.`) | Glasgow — `glasgow.uk.europa.` | `r_glasgow` |
| Regno Unito (`uk.europa.`) | London — `london.uk.europa.` | `r_london` |

## 5. Modello ripetuto per ciascuna delle 37 città

Per la zona cittadina `<citta>.<paese>.europa.` è prevista **questa struttura identica** (l’elenco di tutte le 111 zone concrete compare nell’albero al §3):

```text
<citta>.<paese>.europa.                         [SOA, NS, A, MX]
├── services.<citta>.<paese>.europa.            [SOA, NS, A]
│   ├── portal.services.<citta>.<paese>.europa. [record A, non una zona]
│   └── api.services.<citta>.<paese>.europa.    [record A, non una zona]
├── research.<citta>.<paese>.europa.            [SOA, NS, A]
│   ├── git.research.<citta>.<paese>.europa.    [record A, non una zona]
│   └── data.research.<citta>.<paese>.europa.   [record A, non una zona]
└── admin.<citta>.<paese>.europa.               [SOA, NS, A]
    ├── monitor.admin.<citta>.<paese>.europa.  [record A, non una zona]
    └── logs.admin.<citta>.<paese>.europa.     [record A, non una zona]
```

Nella zona cittadina principale si prevedono `ns1` (A), `www` (A), `api` (A), `mail` (A) e `MX 10 mail.<citta>.<paese>.europa.`. `ns1` qui è un **record del server**, non un dominio delegato. Ogni sottozona usa `ns1.<sottozona>...` come proprio NS, con glue nel genitore quando l’indirizzo NS è interno alla zona figlia. I record A devono puntare a indirizzi reali di host DNS o di servizio aggiunti al lab, **non** automaticamente alla loopback del router.

### Esempio completo: Roma

```text
.
└── europa.
    └── it.europa.
        └── rome.it.europa.
            ├── ns1.rome.it.europa.                         A
            ├── www.rome.it.europa.                         A
            ├── api.rome.it.europa.                         A
            ├── mail.rome.it.europa.                        A (target MX)
            ├── rome.it.europa.                             MX 10 mail.rome.it.europa.
            ├── services.rome.it.europa.                    [delega NS]
            │   ├── ns1.services.rome.it.europa.            A
            │   ├── portal.services.rome.it.europa.         A
            │   └── api.services.rome.it.europa.            A
            ├── research.rome.it.europa.                    [delega NS]
            │   ├── ns1.research.rome.it.europa.            A
            │   ├── git.research.rome.it.europa.            A
            │   └── data.research.rome.it.europa.           A
            └── admin.rome.it.europa.                       [delega NS]
                ├── ns1.admin.rome.it.europa.               A
                ├── monitor.admin.rome.it.europa.           A
                └── logs.admin.rome.it.europa.              A
```

## 6. Scopo dei TLD aggiuntivi

| TLD | Rami delegati | Obiettivo per il benchmark |
|---|---|---|
| `europa.` | 22 paesi → 37 città → 111 sottozone | Molte deleghe profonde, verifica DNS distribuito geograficamente |
| `infra.` | `dns`, `routing`, `monitoring`; sotto `dns`: `root`, `tld`, `resolvers` | Separazione infrastrutture e controlli dei nameserver |
| `research.` | `universities`, `experiments`, `datasets`; sotto `experiments`: `latency`, `failures` | Test su ricerca, latenza e guasti |
| `services.` | `web`, `api`, `mail`; sotto `web`: `portals` | Risoluzione di servizi globali separata dai servizi delle città |
| `lab.` | `benchmark`, `checker`, `clients`; sotto `benchmark`: `scenarios` | Organizzazione logica dei componenti del benchmark |
| `test.` | `positive`, `negative`, `dnssec`; sotto `negative`: `nxdomain`, `delegation` | Casi positivi e controlli negativi; il ramo `dnssec` è solo una zona tematica, non implica DNSSEC attivo |

## 7. Deleghe, SOA/NS, glue e resolver

1. Il nameserver artificiale della radice autoritativa per `.` pubblica le sei deleghe NS per i sei TLD; un suo nome possibile è `a.root-servers.` (il suffisso `root-servers.` **non** è delegato).
2. Ogni zona figlia ha record SOA, NS di apex e A per il suo nameserver. Esempio: `ns1.europa.` è il server nominato per `europa.`; la radice fornisce il glue A corrispondente. Questa convenzione si applica ricorsivamente anche a paese, città e sottozona.
3. Se il nameserver è **in-bailiwick** nella zona delegata, il genitore deve pubblicare il glue A (e AAAA solo se prevista IPv6). I valori devono coincidere con gli IP reali degli host assegnati in fase di implementazione.
4. I server autoritativi useranno `recursion no`; i resolver ricorsivi useranno root hints puntati **solo** alla radice artificiale, senza forwarder verso Internet e con DNSSEC validation disabilitata finché la gerarchia resta non firmata.
5. Le zone funzionali e le zone cittadine sono oggetti DNS logici; non implicano automaticamente 201 dispositivi. Il deploy richiede un piano indirizzi e un’associazione zone → server prima di generare i file BIND.
6. Il backbone attuale contiene solo 37 router: bisogna predisporre i dispositivi DNS/host con la **SkillCreazione**; solo dopo si usa la **Skill DNS** per configurare BIND senza alterare indirizzi e routing esistenti.

## 8. Verifiche proposte

Per ciascuna delle 37 città: query SOA e NS della zona principale, A di `www`, A di `mail`, MX della zona città, A di `portal.services`, A di `git.research`, A di `monitor.admin` (**8 query × 37 = 296 query cittadine**). Ulteriori verifiche sui sei TLD, i 22 domini-paese e le 200 deleghe, sui glue, su NXDOMAIN/REFUSED/SERVFAIL, sui resolver e sulla connettività completano il benchmark.

Non tutte queste verifiche sono eseguibili con i soli check `applications.dns` del checker: per NS, SOA, referral, glue e casi negativi potrebbero servire `custom_commands` con `dig` e asserzioni mirate.

## 9. File allegati e stato implementativo

- `zone_inventory.csv` — inventario delle 201 zone e parent.
- `delegazioni.csv` — tutte le 200 relazioni parent → child e requisiti glue.
- `citta_domini_v2.csv` — mapping 37 città, router e nomi DNS.
- `albero_dns_europa_multi_tld.svg` / `.png` — diagramma preciso, generato dall’inventario (non è la precedente immagine illustrativa).
- **Non creati in questa fase:** `named.conf`, `db.*`, `.startup` DNS, `correction.yaml`: richiedono un piano di host reali e una decisione sul deployment.

## 10. Origine delle informazioni

- **Derivato dal JSON originale:** 37 città/nodi e 57 archi/link (`cost266(1).json`).
- **Derivato dal precedente lavoro:** associazione città → paese/router e alberi iniziali `*.europa.test.`.
- **Nuovo disegno proposto:** sei TLD, tre sottozone per città, 24 zone funzionali e nomi `*.europa.`.
- **Regole operative:** SKILLCreazione.md e SKILL DNS.md del progetto, in particolare separazione tra fase di progettazione, provisioning dei dispositivi e configurazione dei nameserver.
