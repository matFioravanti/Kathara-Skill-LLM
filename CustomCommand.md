I quattro codici proposti distinguono **aspetti diversi della correttezza DNS**: l’autorità sulle zone, le deleghe tra zone, gli indirizzi IPv4 pubblicati e i server di posta dichiarati. Di seguito descrivo ciò che verificano effettivamente i comandi presenti nel repository. I codici restano una proposta: non ho modificato i file. Annotation 1

**CC01 — Autorità delle zone: controlli SOA**

Questa tipologia verifica che il server previsto **risponda come autorevole per una determinata zona**. Nel file sono presenti **49 controlli**, eseguiti da `pc50`.

Il record **SOA**, *Start of Authority*, contiene informazioni amministrative della zona, come server primario, contatto del responsabile, numero di versione e parametri temporali. Il flag **AA**, *Authoritative Answer*, indica una risposta autorevole. [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html#section-3.3.13)

Un esempio del laboratorio è:

```sh
dig @10.16.1.11 . SOA +norecurse
```

La richiesta viene inviata direttamente a `10.16.1.11` e riguarda la zona radice `.`. L’opzione `+norecurse` disattiva la richiesta di ricorsione.

Il custom command considera riuscita la verifica quando:

- la risposta contiene lo stato `NOERROR`;
- nei flag compare `AA`;
- nella sezione delle risposte esiste un record `SOA` con il nome della zona richiesta.

La combinazione dei tre requisiti è significativa: una risposta senza errori, da sola, non dimostra che il server abbia restituito il SOA atteso.

Questo controllo può rilevare, per esempio, una zona non caricata da BIND, una richiesta inviata al server sbagliato oppure un server che restituisce dati senza dichiararsi autorevole.

**Il controllo attuale verifica la presenza del SOA, ma non confronta i suoi valori interni**: un seriale errato o un contatto amministrativo diverso da quello desiderato potrebbero quindi passare.

**CC02 — Deleghe DNS: controlli NS e glue**

Questa tipologia verifica **la coerenza del passaggio da una zona padre a una zona figlia**. Nel file sono presenti **48 controlli**.

Una delega permette al padre di indicare quali nameserver gestiscono la zona figlia. I record **NS** contengono i nomi di questi server. Se un nameserver appartiene alla stessa zona delegata, il padre deve fornire gli indirizzi necessari a raggiungerlo: questi record sono il **glue**, che evita una dipendenza circolare nella risoluzione. [RFC 1034](https://www.rfc-editor.org/rfc/rfc1034.html#section-4.2.1)

Nel primo controllo del laboratorio vengono confrontati:

- il padre, ossia la radice su `10.16.1.11`;
- la zona figlia `com.`, servita da `10.16.1.12`.

Il comando svolge più verifiche consecutive:

1. Interroga il padre e raccoglie gli NS della delega per `com.`.
2. Interroga il server figlio e raccoglie gli NS pubblicati per `com.`.
3. Verifica che l’insieme del padre sia non vuoto e coincida con quello del figlio.
4. Risolve ciascun nome NS attraverso il resolver `10.16.13.12`, verificando l’indirizzo previsto.
5. Quando il nome NS appartiene alla zona figlia, controlla anche il relativo glue IPv4 nella risposta del padre.

Per esempio, se il nameserver fosse `ns.com.`, occorrerebbe conoscere il suo indirizzo per raggiungere il server di `com.`. Il glue pubblicato dal padre fornisce proprio quell’informazione.

Questa tipologia può rilevare deleghe mancanti, nomi NS discordanti tra padre e figlio, indirizzi errati e glue assente o incoerente.

**Nel comando attuale il criterio centrale è la coerenza tra NS e indirizzi**: non viene imposto un nome NS prestabilito, né vengono controllati esplicitamente `NOERROR` e `AA` come nei controlli SOA. Nomi diversi possono quindi superare il controllo se risultano coerenti e risolvono all’indirizzo atteso.

**CC03 — Record A autorevoli**

Questa tipologia verifica che **un determinato nome abbia l’indirizzo IPv4 previsto nella risposta del server autorevole**. Nel file sono presenti **44 controlli**.

Un record **A** associa un nome DNS a un indirizzo IPv4. [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html#section-3.4.1)

Un esempio reale è:

```sh
dig @10.16.2.12 example.com. A +norecurse
```

Il controllo richiede:

- stato `NOERROR`;
- flag `AA`;
- un record con nome `example.com.`, tipo `A` e valore `10.16.2.12`.

Rispetto a CC01, cambia l’informazione verificata: il SOA accerta che il server risponda autorevolmente per la zona; questo controllo accerta che **uno specifico dato pubblicato sia quello atteso**.

Può rilevare un record mancante, un indirizzo sbagliato, un nome scritto in modo errato oppure una risposta non autorevole.

Nel gruppo rientrano anche gli indirizzi dei server di posta, come `mail.company.com.`: rimangono controlli di tipo A perché verificano un’associazione nome–IPv4.

**Il comando cerca la presenza dell’indirizzo atteso, senza escludere eventuali altri indirizzi A**. Se la risposta contenesse sia l’indirizzo corretto sia un indirizzo aggiuntivo indesiderato, questo custom command potrebbe comunque riuscire.

Le interrogazioni partono da `pc50` e indicano esplicitamente il server con `@IP`: non verificano quindi la configurazione DNS locale di pc51–pc60.

**CC04 — Record MX autorevoli**

Questa tipologia verifica che **un dominio dichiari il server di posta e la preferenza previsti**. Nel file sono presenti **4 controlli**.

Un record **MX**, *Mail Exchange*, contiene una preferenza numerica e il nome del server destinato a ricevere posta per il dominio. Tra più destinazioni, i valori numerici più bassi hanno precedenza. [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html#section-3.3.9)

Per esempio:

```dns
company.com. IN MX 10 mail.company.com.
```

Nel laboratorio il comando interroga direttamente il server autorevole:

```sh
dig @10.16.2.13 company.com. MX +norecurse
```

Per riuscire deve trovare:

- stato `NOERROR`;
- flag `AA`;
- un record MX per `company.com.`;
- preferenza `10`;
- destinazione `mail.company.com.`.

Può quindi rilevare un MX mancante, una preferenza errata o una destinazione diversa da quella richiesta.

Il controllo A associato a `mail.company.com.` verifica separatamente l’indirizzo del server dichiarato. I due controlli coprono così due informazioni distinte: **quale server riceve la posta** e **a quale IPv4 corrisponde quel server**.

**Questi controlli non provano l’invio o la ricezione della posta**: non aprono una connessione SMTP e non verificano che un servizio mail sia attivo. Inoltre, come per i record A, il comando verifica la presenza dell’MX atteso senza escludere altri MX aggiuntivi.

Il custom MX aggiunge soprattutto **la verifica diretta della risposta del server autorevole**. **Priorità e nome del server di posta sono già verificati dal controllo standard.**

Ho confrontato il custom con [DNSRecordCheck.py](/Users/matthew/Desktop/Tesi-Skill/.venv/lib/python3.14/site-packages/kathara_lab_checker/checks/applications/dns/DNSRecordCheck.py:22) installato nel progetto:

| Aspetto | Controllo standard MX | Custom MX |
|---|---|---|
| Origine della richiesta | Ogni client pc51–pc60 | `pc50` |
| Server interrogato | Resolver configurato sul client | Server autorevole indicato esplicitamente |
| Modalità | Risoluzione ordinaria | Richiesta senza ricorsione |
| Priorità e destinazione MX | Verificate | Verificate |
| Stato `NOERROR` | Non controllato esplicitamente | Richiesto |
| Flag autorevole `AA` | Non controllato | Richiesto |

Per esempio, lo standard esegue sui client:

```sh
dig +short MX company.com
```

e confronta l’output con `10 mail.company.com.`. Verifica quindi che **il client ottenga il valore atteso attraverso il proprio percorso di risoluzione**, che può includere la cache del resolver.

Il custom interroga invece direttamente l’autorevole:

```sh
dig @10.16.2.13 company.com. MX +norecurse
```

e richiede che quel server risponda con `NOERROR`, `AA` e l’MX atteso. Questo permette di rilevare, per esempio, un problema sull’autorevole anche quando il resolver conserva ancora una risposta corretta in cache.

C’è anche una differenza nel confronto: lo standard confronta l’intero output testuale con uno dei valori configurati; il custom cerca **la presenza dell’MX atteso**, quindi può accettare altri MX aggiuntivi.

I due controlli sono dunque complementari: lo standard verifica la risoluzione dai client, il custom controlla direttamente la pubblicazione autorevole. Nessuno dei due verifica il funzionamento SMTP.

STANDARD

Ho assegnato i codici **CS01–CS11** ai controlli standard nelle correction [small](/Users/matthew/Desktop/Tesi-Skill/scenarios/lab_01/tasks/base/small/correction.yaml), [medium](/Users/matthew/Desktop/Tesi-Skill/scenarios/lab_02/tasks/base/medium/correction.yaml) e [large](/Users/matthew/Desktop/Tesi-Skill/scenarios/lab_03/tasks/base/large/correction.yaml), aggiungendo titoli e spiegazioni nei commenti.

| Codice | Titolo | Cosa verifica e a cosa serve |
|---|---|---|
| **CS01** | **Presenza dei dispositivi** | Controlla che tutti i router e PC definiti in `lab_inline` esistano nel laboratorio. Rileva dispositivi mancanti o con nomi diversi da quelli richiesti. |
| **CS02** | **Collegamenti e domini di collisione** | Confronta il collegamento di ogni interfaccia con la topologia attesa. Rileva, per esempio, un PC collegato alla LAN sbagliata o un’interfaccia del router associata al collegamento errato. |
| **CS03** | **Presenza degli script di avvio** | Verifica che esistano i file `<dispositivo>.startup` richiesti. Serve a controllare che la configurazione di avvio sia stata predisposta; non verifica la correttezza del contenuto degli script. |
| **CS04** | **Indirizzi IP e prefissi delle interfacce** | Legge gli indirizzi effettivamente configurati e confronta dispositivo, interfaccia, IP e prefisso. Rileva indirizzi sbagliati, maschere errate o indirizzi assegnati all’interfaccia sbagliata. |
| **CS05** | **Processi richiesti e vietati** | Usa `pgrep` per verificare quali processi sono presenti. Per esempio, `named` deve essere attivo dove richiesto; `!named` ne richiede l’assenza. Serve anche a verificare che non vengano usati demoni di routing vietati. |
| **CS06** | **Tabella di instradamento** | Confronta le destinazioni delle rotte, escludendo quelle direttamente connesse. Segnala rotte mancanti o aggiuntive. Nelle correction attuali non sono specificati vincoli su gateway e interfaccia di uscita. |
| **CS07** | **Raggiungibilità IP** | Esegue un ping per ogni coppia sorgente–destinazione indicata. Verifica che la rete permetta effettivamente lo scambio di pacchetti, oltre alla correttezza delle singole configurazioni. |
| **CS08** | **Server DNS autorevoli attesi** | Interroga i record NS e risolve i nomi dei nameserver per cercare l’indirizzo autorevole previsto. Per la radice esegue verifiche anche dal resolver. Non richiede esplicitamente il flag `AA`, verificato invece dai custom appropriati. |
| **CS09** | **Resolver DNS configurato sui client** | Controlla che `/etc/resolv.conf` dei client contenga il nameserver atteso. Rileva un resolver mancante o sbagliato; la sua presenza nel file non dimostra da sola che funzioni. |
| **CS10** | **Risoluzione dei record A dai client** | Esegue `dig +short A` sui client elencati in `local_ns` e confronta la risposta con i valori configurati. Verifica che il percorso di risoluzione usato dai client restituisca gli IPv4 attesi. |
| **CS11** | **Risoluzione dei record MX dai client** | Esegue `dig +short MX` dagli stessi client e confronta preferenza e nome del server di posta. Verifica la risoluzione DNS degli MX; non prova connessioni SMTP o consegna della posta. |

**CS01 e CS02 derivano entrambi da `lab_inline`**: il checker usa quel modello per verificare separatamente dispositivi e collegamenti. `convergence_time` e `default_image` restano parametri di esecuzione, quindi non hanno ricevuto un codice di controllo.

Le modifiche riguardano **solo i commenti**: dati YAML, comandi custom e ordine dei controlli sono identici a prima. Tutti e tre i file superano il parser ufficiale del checker e `git diff --check`.

Come per i codici CC, queste etichette identificano i gruppi nel YAML; non cambiano automaticamente i nomi nei report.