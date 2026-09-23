---
name: kathara-dns-configuration
description: "Analizza un laboratorio Kathara esistente e configura direttamente DNS e servizi web opzionali a partire da vincoli positivi e negativi. Preserva la topologia, l'indirizzamento e il routing esistenti; assegna i ruoli DNS, costruisce zone e deleghe e modifica direttamente i file persistenti del laboratorio."
argument-hint: "lab_path, requisiti DNS/web in linguaggio naturale e opzioni operative facoltative"
user-invocable: true
---

# Configurazione DNS automatizzata in Kathara

Questa skill è progettata per essere caricata da uno script Python che orchestra l'LLM. L'LLM accede direttamente al laboratorio, ne analizza i file e applica autonomamente le modifiche richieste.

Il laboratorio esiste già e la sua topologia è descritta da `lab.conf`. Topologia, indirizzamento, forwarding e routing sono input immutabili: possono essere analizzati per posizionare correttamente resolver, server autoritativi e flussi DNS correlati, ma non devono essere generati o modificati da questa skill.

## Riferimenti autorevoli

### Kathara

- Riferimento principale dei comandi: https://www.kathara.org/man-pages/kathara.1.html
- Configurazione dello scenario di rete (`lab.conf`): https://www.kathara.org/man-pages/kathara-lab.conf.5.html
- Struttura delle directory dello scenario di rete: https://www.kathara.org/man-pages/kathara-lab-dirs.7.html
- Esecuzione di comandi in un dispositivo: https://www.kathara.org/man-pages/kathara-exec.1.html
- Scenari di rete ufficiali: https://github.com/KatharaFramework/Kathara-Labs
- Directory ufficiale dei laboratori DNS: https://github.com/KatharaFramework/Kathara-Labs/tree/main/main-labs/application-level/dns
- Laboratorio ufficiale integrato DNS + web server: https://github.com/KatharaFramework/Kathara-Labs/tree/main/main-labs/labs-integrating-several-technologies/small-internet-with-dns-and-web-server
- Kathara Lab Checker: https://github.com/KatharaFramework/kathara-lab-checker
- Immagini Docker ufficiali: https://github.com/KatharaFramework/Docker-Images/tree/develop

### BIND 9 e DNS

- BIND 9 Administrator Reference Manual: https://bind9.readthedocs.io/en/stable/
- Riferimento BIND 9.11: https://ftp.ripe.net/mirrors/sites/ftp.isc.org/isc/bind/9.11.5/doc/arm/Bv9ARM.ch06.html
- Riferimento attuale della configurazione BIND: https://bind9.readthedocs.io/en/stable/reference.html
- Pagine di manuale BIND: https://bind9.readthedocs.io/en/stable/manpages.html
- RFC 1034: https://datatracker.ietf.org/doc/html/rfc1034
- RFC 1035: https://datatracker.ietf.org/doc/html/rfc1035

Prima di usare un'opzione BIND non trattata qui, verificarne la sintassi nella documentazione ufficiale compatibile con la versione rilevata nel laboratorio.

## Concetti essenziali

- Un laboratorio Kathara è incentrato su `lab.conf`, con script `<device>.startup` opzionali e directory persistenti per dispositivo.
- La directory di un dispositivo rispecchia il filesystem root del dispositivo: `ns1/etc/bind/named.conf` diventa `/etc/bind/named.conf` all'interno di `ns1`.
- Le modifiche devono essere persistenti nei file del laboratorio; non fare affidamento su modifiche interattive effettuate nei container.
- Un dominio di collisione collega le interfacce ma non assegna automaticamente indirizzi, route o ruoli DNS.
- Un root name server è autoritativo per `.`; un resolver che contiene root hints non è un root name server.
- Un server autoritativo pubblica dati per una o più zone; un resolver locale/ricorsivo segue le deleghe e risponde ai client.
- Un record `NS` da solo non rende una macchina un name server funzionante.
- Una risoluzione DNS riuscita non implica che il servizio associato sia raggiungibile.

## Contratto di esecuzione

Lo script Python fornisce almeno:

- `lab_path`;
- la specifica DNS/web in linguaggio naturale;
- eventuali opzioni operative.

L'LLM opera direttamente sotto `lab_path`.

Regole:

1. Non fare domande durante l'esecuzione automatizzata.
2. Analizzare completamente il laboratorio e verificarne la fattibilità prima della prima modifica.
3. Se mancano dati indispensabili o i requisiti sono in conflitto, non modificare il laboratorio e restituire un errore conciso.
4. Se la configurazione è fattibile, creare o modificare direttamente solo i file persistenti richiesti dai ruoli effettivamente assegnati a ciascun dispositivo.
5. Non modificare topologia, indirizzi, forwarding o route.
6. Non creare `dns-plan.yaml`, JSON intermedi, file di pianificazione o file di test.
7. Al termine, restituire soltanto un riepilogo conciso delle modifiche applicate oppure dell'errore bloccante.

## Compatibilità delle immagini

Rilevare prima l'immagine e la versione dichiarate in `lab.conf`; preservare le immagini esistenti quando forniscono già il software richiesto.

| Scopo | Immagini normalmente compatibili |
|---|---|
| Host/router generico | `kathara/core`, `kathara/base` |
| DNS con BIND 9 | `kathara/bind`, `kathara/bind:9.11`, `kathara/bind:9.11.5`, `kathara/base` |
| Web con Apache | `kathara/apache`, `kathara/base` |
| DNS + web sullo stesso dispositivo | `kathara/base` |

Con BIND 9.11 usare una sintassi compatibile: `type master`, `type slave` e `masters`. Non sostituire automaticamente immagini o tag compatibili e non inserire `apt install` negli script di startup.

## Regole globali

- Preservare la topologia dichiarata in `lab.conf`.
- Trattare indirizzamento, forwarding e routing come sola lettura.
- Configurare IPv4 e IPv6 in modo indipendente.
- Non assegnare mai un ruolo DNS vietato dalla specifica.
- Non indebolire mai un requisito negativo per soddisfarne uno positivo.
- Non usare un `SERVFAIL` accidentale come meccanismo intenzionale di negazione.
- Usare FQDN con punto finale nei file di zona quando un nome è assoluto.
- Usare root hints per la gerarchia artificiale, non root hints di Internet pubblico.
- Per una root artificiale intenzionalmente non firmata, disabilitare la validazione DNSSEC salvo che DNSSEC sia richiesto esplicitamente.
- Applicare la modifica coerente minima e preservare contenuti, commenti e configurazioni non correlati.
- Trattare ogni directory `<device>/` come un overlay persistente sparso del filesystem: creare soltanto i percorsi richiesti dai ruoli effettivamente assegnati a quel dispositivo e non creare mai directory specifiche di un ruolo solo per simmetria.
- Usare `systemctl` per avviare i servizi dagli script di startup.
- Non dichiarare risultati runtime che non siano stati osservati.

## Tenere separati i tre piani

Per ogni requisito distinguere:

1. **Risoluzione DNS**: client → resolver locale → root/server autoritativi.
2. **Applicazione**: client → indirizzo del servizio restituito dal DNS.
3. **Routing esistente**: percorso imposto dalla configurazione di livello 3.

Questi aspetti non sono equivalenti:

- `pc1` risolve `www.example.test.`;
- `pc1` raggiunge l'indirizzo restituito;
- il traffico HTTP di `pc1` attraversa `r4`;
- le query del resolver verso il server autoritativo attraversano `r4`.

Il routing è un vincolo sul posizionamento dei ruoli e sui flussi DNS/web, non una configurazione da riscrivere.

## Interpretazione dei requisiti

Accettare specifiche scritte in italiano o inglese, inclusa prosa lunga. Preservare esattamente nomi dei dispositivi, nomi delle interfacce, etichette dei domini di collisione, FQDN e identificatori tecnici; normalizzare internamente soltanto maiuscole/minuscole DNS e il punto finale degli FQDN.

### Tipi di requisito DNS

| Tipo | Significato |
|---|---|
| `role-required` | Un dispositivo deve svolgere un ruolo DNS. |
| `role-forbidden` | Un dispositivo non deve svolgere uno o più ruoli DNS. |
| `authority` | Un dispositivo deve o non deve essere autoritativo per una zona. |
| `resolution` | Un client o gruppo deve ottenere un risultato specifico per QNAME/QTYPE. |
| `resolver-use` | Un client deve o non deve usare un resolver locale. |
| `query-waypoint` | Un flusso client→resolver o resolver→server autoritativo deve attraversare router specificati. |
| `query-avoidance` | Un flusso DNS deve evitare router specificati. |
| `delegation` | Una zona padre deve delegare una zona figlia ai server autoritativi selezionati. |

Ruoli supportati:

- `root-authoritative`;
- `zone-authoritative`;
- `recursive-resolver`;
- `secondary-authoritative`;
- `dns-client`.

Esempi:

- Tutti i client devono risolvere `www.example.test.` con A e AAAA.
- `pc3` non deve essere un name server.
- `server2` può essere autoritativo per `example.test.` ma non per `.`.
- `pc2` deve ricevere `REFUSED` per `private.test.`.
- `pc1` deve usare `ldns1`.
- Le query da `ldns1` verso il server autoritativo per `example.test.` devono attraversare `r4`.

### Tipi di requisito web

| Tipo | Significato |
|---|---|
| `web-publish` | Un FQDN deve mappare agli indirizzi reali del web server. |
| `web-reachability` | I client specificati devono o non devono completare una richiesta HTTP. |
| `web-waypoint` | Il traffico client→web server deve includere o evitare i router specificati. |

### Semantica normativa

- “A può risolvere X” richiede `NOERROR` e i record richiesti tramite il resolver assegnato ad A.
- “A non può risolvere la zona Z” normalmente significa `REFUSED` intenzionale; usare `NXDOMAIN` solo quando il nome deve apparire inesistente.
- Un timeout è appropriato solo quando il requisito richiede esplicitamente irraggiungibilità di rete.
- `SERVFAIL` indica una catena interrotta o un errore del server.
- “M non può essere un name server” vieta a M i ruoli di autorità root, autorità non-root, secondario e resolver ricorsivo.
- “M non può essere root” vieta soltanto l'autorità per `.`.
- “Tutte le macchine possono risolvere” si applica agli endpoint che ci si aspetta agiscano come client DNS; i router di puro transito sono inclusi solo quando esplicitamente richiesto.
- Un vincolo di percorso riferito a un FQDN si applica al traffico applicativo verso l'indirizzo risolto, salvo che faccia esplicitamente riferimento alla query DNS.
- Non generare reverse DNS o DNSSEC salvo richiesta.
- Usare un solo primario per zona nella configurazione minima; aggiungere secondari solo quando richiesto.

## Procedura

### 1) Analizzare il laboratorio e costruire il modello di rete

Leggere direttamente:

- `lab.conf`;
- i file `*.startup` e gli eventuali `*.shutdown`;
- le directory persistenti per dispositivo;
- la configurazione BIND esistente, `resolv.conf` e i contenuti web.

Derivare dispositivi, immagini, interfacce, domini di collisione, indirizzi IPv4/IPv6, route e configurazione di forwarding esistente.

Costruire una vista interna di livello 3 in sola lettura, separatamente per IPv4 e IPv6. Usare le route esistenti, il longest-prefix match e i percorsi di ritorno quando necessario per determinare:

- client → resolver;
- resolver → root;
- resolver → server autoritativo;
- waypoint richiesti/vietati;
- raggiungibilità del web server.

Non modificare ancora i file. Se dati indispensabili non sono disponibili, interrompere.

### 2) Analizzare requisiti, namespace e fattibilità

Convertire la specifica in vincoli DNS/web espliciti e costruire l'albero del namespace.

Per i nomi assoluti usare internamente FQDN normalizzati con punto finale. Preservare i tagli di zona espliciti. Se i tagli non sono specificati:

1. `.` è una zona;
2. ogni dominio di primo livello sotto `.` è una zona delegata;
3. ogni dominio organizzativo di secondo livello che contiene record host/servizio è una zona delegata;
4. le etichette più profonde restano nella zona organizzativa più vicina, salvo diversa indicazione di un altro requisito.

Non trasformare automaticamente ogni nodo del namespace in una zona.

Prima di modificare il laboratorio, verificare che esista almeno una soluzione che soddisfi tutti i vincoli. La configurazione è, per esempio, non fattibile quando:

- nessun dispositivo consentito può agire come autorità root;
- una zona necessita di un'autorità ma nessun dispositivo può essere un name server;
- un resolver obbligatorio non è raggiungibile dai client richiesti;
- la catena richiesta non esiste sulla famiglia di indirizzi richiesta;
- lo stesso client/QNAME/QTYPE deve sia riuscire sia fallire nelle medesime condizioni;
- lo stesso flusso deve sia attraversare sia evitare lo stesso waypoint;
- nessun resolver può raggiungere una catena di delega completa.

Se non è fattibile, interrompere prima delle modifiche e restituire la motivazione tecnica.

### 3) Assegnare i ruoli DNS e derivare i flussi

Scegliere soltanto dispositivi consentiti con indirizzi stabili già esistenti.

L'autorità root deve essere raggiungibile dai resolver pertinenti e in grado di servire `.`.

Per ogni zona non-root selezionare almeno un'autorità raggiungibile dai resolver pertinenti.

Ogni resolver locale deve:

- essere raggiungibile dai client assegnati;
- raggiungere almeno un'autorità root;
- raggiungere almeno un'autorità a ogni livello di delega;
- rispettare i vincoli relativi a famiglia di indirizzi, waypoint ed evitamento.

Se un singolo resolver non può coprire tutti i client, usare il numero minimo consentito di resolver.

Quando le assegnazioni sono equivalenti, preferire in quest'ordine:

1. dispositivi server dedicati;
2. endpoint che non siano router;
3. dispositivi dual-stack;
4. dispositivi con meno ruoli già esistenti;
5. il nome di dispositivo lessicograficamente più piccolo.

Considerare questi flussi:

1. client → resolver, UDP/TCP 53;
2. resolver → root, UDP/TCP 53;
3. resolver → autorità delegate, UDP/TCP 53;
4. primario → secondario, TCP 53, quando richiesto;
5. client → web server, TCP 80/443, quando richiesto.

Non assumere che un client stub contatti direttamente i server autoritativi durante la normale risoluzione ricorsiva.

### 4) Costruire zone, deleghe e record

Per ogni zona derivare:

- SOA;
- NS all'apice;
- dati A/AAAA per i name server;
- record host e di servizio;
- deleghe delle zone figlie;
- glue A/AAAA quando richiesti.

Per `child.parent.`:

- il parent contiene l'NS di delega;
- il parent contiene il glue quando il target NS è in-bailiwick;
- il child contiene i propri record SOA e NS;
- il server selezionato carica effettivamente la zona figlia.

Non usare indirizzi IP come target NS, non usare un CNAME come target NS e non inserire un CNAME in un apex che contiene anche dati SOA/NS.

### 5) Preservare layout e struttura persistente

Adattare la generazione al layout già usato dal laboratorio. Non imporre `named.conf.local`, una directory `zones/` o `root.hints` quando il laboratorio usa un'altra struttura.

La directory di un dispositivo Kathara è un **overlay persistente sparso** del filesystem root di quel dispositivo. Per esempio:

```text
pc1/etc/bind/named.conf
```

diventa:

```text
/etc/bind/named.conf
```

all'interno di `pc1`.

L'albero delle directory persistenti deve essere determinato dai ruoli effettivamente assegnati a ciascun dispositivo. **Non** creare la stessa struttura di directory su ogni host.

Usare questa mappatura ruolo→percorso:

| Ruolo del dispositivo | Percorso persistente normalmente richiesto |
|---|---|
| DNS root autoritativo | `<device>/etc/bind/` |
| DNS autoritativo non-root | `<device>/etc/bind/` |
| DNS ricorsivo/locale | `<device>/etc/bind/` |
| Client DNS stub | `<device>/etc/resolv.conf` |
| Web server | `<device>/var/www/html/` |
| Router/nodo di transito puro | nessun percorso persistente DNS/web salvo richiesta esplicita |

Se un dispositivo svolge più ruoli, creare l'**unione** dei percorsi richiesti da quei ruoli.

Un layout minimo basato sui ruoli può quindi apparire così:

```text
lab/
├── lab.conf
│
├── ldns.startup
├── ldns/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.root
│
├── root.startup
├── root/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.root
│
├── auth.startup
├── auth/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.<zone>
│
├── client/
│   └── etc/resolv.conf
│
└── web/
    └── var/www/html/
        └── index.html
```

Interpretazione:

- sul resolver locale, `db.root` può contenere i root hints per la gerarchia artificiale;
- sul root name server, `db.root` può essere il file autoritativo per la zona `.`;
- il ruolo è determinato dalla dichiarazione `zone` in `named.conf`, non dal nome del file;
- i file di zona autoritativi possono risiedere direttamente sotto `/etc/bind/` quando questa è la convenzione del laboratorio;
- la configurazione del resolver di un client stub può essere resa persistente direttamente con `<client>/etc/resolv.conf`.

#### Regole per il layout sparso

Applicare tutte le seguenti regole:

1. Creare `<device>/etc/bind/` solo quando quel dispositivo esegue effettivamente BIND come server autoritativo, resolver ricorsivo, secondario o altro ruolo DNS-server richiesto esplicitamente.
2. Creare `<device>/etc/resolv.conf` solo quando quel dispositivo deve comportarsi come **client DNS stub** tramite il resolver locale selezionato.
3. Non creare `resolv.conf` soltanto perché un dispositivo:
   - dispone di connettività IPv4 o IPv6;
   - esegue BIND;
   - è autoritativo per una zona;
   - è il resolver ricorsivo;
   - ospita un servizio web.
4. Un resolver ricorsivo **non** necessita di un `resolv.conf` che punti a sé stesso, salvo che la specifica richieda esplicitamente che l'host stesso effettui risoluzione stub tramite quel resolver.
5. Un server DNS autoritativo **non** necessita automaticamente di `resolv.conf`.
6. Un web server **non** necessita automaticamente di `resolv.conf`; aggiungerlo solo se lo stesso dispositivo è anche un client DNS richiesto.
7. Non creare `/etc/bind/` su client puri o web server puri.
8. Non creare `/var/www/html/` su dispositivi che non ospitano un servizio web.
9. Non creare directory di ruolo vuote.
10. Non creare copie placeholder di file BIND su dispositivi che non caricano quei file.
11. Preservare file e directory persistenti esistenti non correlati.
12. Preferire modifiche locali sicure ai file esistenti e non eliminare file salvo necessità esplicita.

Prima di scrivere file, derivare una mappa interna ruolo→filesystem come:

```text
root1 -> DNS authoritative -> etc/bind/
auth1 -> DNS authoritative -> etc/bind/
ldns1 -> recursive resolver -> etc/bind/
pc3   -> DNS client         -> etc/resolv.conf
web1  -> web server         -> var/www/html/
```

Usare tale mappa per decidere quali directory e file sia lecito creare. La struttura persistente finale deve essere la struttura minima che implementa completamente i ruoli richiesti.

#### Separazione dei file BIND

Se il laboratorio non dispone di una configurazione BIND esistente, usare questa struttura:

- `named.conf`: solo dichiarazioni `include` e `zone`.
- `named.conf.options`: opzioni globali, ACL, ricorsione, `allow-recursion`, `listen-on` e impostazioni DNSSEC.
- `db.root`: root hints sul resolver oppure zona root autoritativa sul root server.
- `db.<zone>`: record per la corrispondente zona autoritativa.

Non inserire ACL o blocchi `options` direttamente all'interno di `named.conf`.

### 6) Configurare i server BIND autoritativi

Adattare la sintassi alla versione BIND rilevata.

Esempio di autorità root BIND 9.11:

```conf
include "/etc/bind/named.conf.options";

zone "." {
    type master;
    file "/etc/bind/db.root";
};
```

Esempio di autorità non-root:

```conf
include "/etc/bind/named.conf.options";

zone "es" {
    type master;
    file "/etc/bind/db.es";
};
```

Opzioni autoritative minime:

```conf
options {
    directory "/var/cache/bind";
    recursion no;
};
```

Aggiungere direttive `allow-query`, `allow-transfer`, `listen-on`, `listen-on-v6` o DNSSEC solo quando richieste o necessarie per compatibilità.

Per un secondario BIND 9.11 richiesto esplicitamente:

```conf
zone "example.test" {
    type slave;
    masters { <MASTER_IPV4>; <MASTER_IPV6>; };
    file "/var/cache/bind/db.example.test";
};
```

Il master deve consentire i trasferimenti solo agli indirizzi secondari selezionati.

### 7) Generare i file di zona

Usare soltanto nomi e indirizzi presenti nella specifica o nel laboratorio.

Esempio di autorità root che delega `es.`:

```dns
$TTL 70000
@   IN SOA ROOT-SERVER. root.ROOT-SERVER. (
        2026091901
        28800
        14400
        3600000
        0
)

@               IN NS ROOT-SERVER.
ROOT-SERVER.    IN A  <ROOT_IPV4>

es.             IN NS dnses.es.
dnses.es.       IN A  <ES_AUTH_IPV4>
```

`dnses.es. A ...` è un glue perché il name server della zona delegata appartiene alla zona figlia.

Esempio di zona `es`:

```dns
$TTL 70000
@   IN SOA dnses.es. root.dnses.es. (
        2026091901
        28800
        14400
        3600000
        0
)

@               IN NS   dnses.es.
dnses.es.       IN A    <AUTH_IPV4>
web.es.         IN A    <WEB_IPV4>
ipv6-web.es.    IN AAAA <WEB_IPV6>
```

Regole:

- incrementare il serial quando si modifica una zona esistente;
- pubblicare A e/o AAAA solo per famiglie di indirizzi effettivamente esistenti e richieste;
- inserire i dati di delega nel parent e i dati autoritativi nel child;
- generare glue solo quando richiesti;
- non inventare mai indirizzi, nomi o livelli gerarchici aggiuntivi.

### 8) Configurare il DNS ricorsivo/locale

Il name server locale usa root hints per la gerarchia artificiale e segue le deleghe. Non ospitare copie autoritative delle zone soltanto per abbreviare la risoluzione.

Esempio di `named.conf`:

```conf
include "/etc/bind/named.conf.options";

zone "." {
    type hint;
    file "/etc/bind/db.root";
};
```

Root hints minimi in `db.root`:

```dns
.              IN NS ROOT-SERVER.
ROOT-SERVER.   IN A  <ROOT_IPV4>
```

Aggiungere AAAA solo quando la root dispone effettivamente di IPv6 e tale famiglia è richiesta.

Esempio di opzioni:

```conf
options {
    directory "/var/cache/bind";
    allow-recursion { <CLIENT_PREFIXES>; };
    dnssec-validation no;
};
```

Con BIND 9.11, preservare eventuali direttive legacy già richieste dal laboratorio.

Distinzione fondamentale:

- `zone "." { type hint; ... }` sul resolver = bootstrap;
- `zone "." { type master; ... }` sul root server = autorità per `.`.

### 9) Implementare policy DNS negative

| Requisito | Meccanismo preferito | Risultato |
|---|---|---|
| Client non autorizzato a ricorsione/cache | `allow-recursion` e, quando necessario, `allow-query-cache` | `REFUSED` |
| Sorgente immediata non autorizzata per una zona | `allow-query` a livello di zona | `REFUSED` |
| Client dietro resolver condiviso con policy specifica per client | view/policy lato resolver oppure resolver separato | `REFUSED` o `NXDOMAIN` |
| Client diversi devono vedere dati diversi | `view` BIND sul server che riceve direttamente la query | dipende dalla view |
| Nome inesistente per tutti | omettere il record autoritativo | `NXDOMAIN` |
| Server intenzionalmente irraggiungibile | solo quando esplicitamente richiesto | timeout |
| Dispositivo che non può essere un name server | nessun ruolo BIND e nessun record NS | ruolo assente |
| Dispositivo che non può essere root | nessuna zona `.` master/primary | ruolo assente |

ACL e view vedono la sorgente DNS immediata: un server autoritativo interrogato da un resolver condiviso vede il resolver, non il client stub originale.

Non interrompere una delega solo per produrre artificialmente un fallimento.

### 10) Configurare i resolver dei client

Configurare `resolv.conf` **solo** sui dispositivi che l'analisi dei requisiti ha classificato come client DNS stub.

Non dedurre il ruolo `dns-client` solo perché un dispositivo ha un indirizzo IP o partecipa al laboratorio. L'esecuzione di un server autoritativo, di un resolver ricorsivo o di un web server non implica automaticamente che l'host sia un client DNS.

Quando il laboratorio usa filesystem persistenti per dispositivo, preferire:

```text
<client>/etc/resolv.conf
```

Contenuto IPv4 minimo:

```text
nameserver <LOCAL_DNS_IPV4>
```

Contenuto IPv6 minimo quando il client deve raggiungere il resolver tramite IPv6:

```text
nameserver <LOCAL_DNS_IPV6>
```

Se entrambe le famiglie di indirizzi sono richieste esplicitamente per lo stesso client stub, includere solo gli indirizzi del resolver effettivamente configurati e raggiungibili da quel client.

Regole:

- aggiungere un nameserver IPv6 solo quando il resolver possiede effettivamente quell'indirizzo IPv6 e il client deve usarlo tramite IPv6;
- usare `search` solo quando è richiesta la risoluzione di nomi brevi;
- non aggiungere resolver pubblici;
- non aggiungere direttamente indirizzi di server autoritativi al `resolv.conf` del client, salvo che quel server sia anche assegnato esplicitamente al ruolo di resolver ricorsivo/locale;
- non generare `resolv.conf` per server root o autoritativi solo perché eseguono BIND;
- non generare `resolv.conf` per il resolver ricorsivo soltanto per farlo puntare a sé stesso;
- non generare `resolv.conf` per un web server salvo che quel dispositivo sia anche un client DNS richiesto.

Se `resolv.conf` è già persistente su un dispositivo che deve essere un client DNS, modificarlo direttamente e preservare il contenuto compatibile non correlato. Generarlo tramite startup solo quando questa è già la convenzione del laboratorio o quando non è disponibile un file persistente.

### 11) Configurare l'avvio dei servizi

Aggiungere comandi di startup solo ai dispositivi che ospitano effettivamente il servizio, preservando lo stile già usato dal laboratorio.

Esempi:

```bash
systemctl start bind9
```

```bash
systemctl start apache2
```

Non duplicare `start`/`restart`, non avviare BIND con `named -g &`, non nascondere gli errori con `|| true` e non inserire test runtime negli script di startup.

### 12) Configurare servizi web opzionali

- Non sovrascrivere contenuti web esistenti salvo richiesta esplicita.
- Se è richiesto un endpoint e `index.html` non esiste, creare contenuto minimo e deterministico in `<web-device>/var/www/html/index.html`.
- Pubblicare A e AAAA solo per le famiglie di indirizzi configurate sul web server.
- I web server IPv4 e IPv6 possono essere dispositivi diversi.
- Configurare un virtual host solo quando richiesto da nomi, porte o `ServerName`.
- Preservare eventuali comandi Apache già esistenti negli script di startup.
- Un web server puro richiede soltanto i propri file del servizio web e le modifiche di startup; non creare `/etc/bind/` o `/etc/resolv.conf` salvo che quel dispositivo abbia anche il corrispondente ruolo DNS-server o DNS-client.

## Applicazione diretta e risultato finale

Dopo aver completato l'analisi e la verifica di fattibilità, applicare direttamente le modifiche richieste sotto `lab_path`. Rendere le modifiche idempotenti quando possibile; se un'operazione fallisce a metà, indicare quali file sono già stati modificati.

Al termine restituire un riepilogo conciso in testo semplice contenente:

- `SUCCESS`, `BLOCKED` o `ERROR`;
- file creati;
- file modificati;
- principali assegnazioni dei ruoli DNS;
- eventuali avvisi o motivazioni bloccanti.

Esempio:

```text
SUCCESS
Created:
- pc1/etc/bind/db.root
Modified:
- pc1/etc/bind/named.conf
- pc3/etc/resolv.conf
Assignments:
- local resolver: pc1
- root authority: pc2
- authority for es.: pc5
```

Se la generazione non è fattibile:

```text
BLOCKED
Reason: no device allowed to act as resolver can reach the authority for zone es. through the existing routing.
```

Non restituire JSON e non delegare allo script Python la scrittura dei file DNS.

## Criteri finali

Prima di terminare, assicurarsi soltanto che:

- ogni requisito DNS/web sia stato considerato;
- topologia, indirizzamento, forwarding e routing restino invariati;
- ruoli, deleghe, glue, record e resolver dei client siano coerenti;
- ogni modifica richiesta sia persistente nei file del laboratorio;
- ogni directory di dispositivo contenga soltanto percorsi persistenti richiesti dal ruolo, senza `etc/bind`, `resolv.conf`, directory web o file placeholder non necessari;
- il contenuto non correlato sia stato preservato;
- il riepilogo finale riporti soltanto operazioni effettivamente eseguite.
