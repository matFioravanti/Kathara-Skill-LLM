# Validazione di `enforced_read_v1` — 29 ottobre 2026

## Esito complessivo: PARTIALLY_VERIFIED

Il pilota isolato ha dimostrato una lettura completa verificata, il blocco reale
di una scrittura anticipata e la ripresa della **stessa sessione Codex** in un
secondo ambiente scrivibile, seguita da una modifica riuscita. Il controllo
negativo ha bloccato il gate senza avviare B. Questo non certifica il protocollo
di produzione: manca l'integrazione dell'orchestrazione nel runner ordinario e
la verifica completa di tutti i possibili canali alternativi del template.
`enforce_or_block()` rimane intenzionalmente fail-closed con `unsupported_backend`.
Non è stato eseguito un checker su una run completa del nuovo protocollo.

La certificazione distingue `CERTIFIED` (tutte le componenti verificate),
`PARTIALLY_VERIFIED` (componenti superate e verifiche mancanti), `FAILED`
(violazione o errore dimostrato) e `NOT_RUN` (nessuna componente verificata).
Una lettura integrale osservata dimostra la restituzione dei byte attesi, non
la comprensione né la corretta applicazione della Skill a un laboratorio DNS.

## Codice e ambiente

Commit di partenza: `594bed43349b48cb373dd602eac33bb70de08aa4`, più le modifiche
locali di questa validazione, senza commit o push automatici. Le versioni finali
dei file modificati sono identificate da `skill_gate_code_versions.json`.
Il precedente rapporto è conservato in `skill_gate_validation_previous.md`;
i vecchi log in `skill_gate_pilot/` non sono stati riscritti.

- macOS, Python globale e virtualenv 3.14.6; pytest 9.1.1; `.venv` del progetto.
- Codex host 0.157.1, Codex nel template 0.149.1.
- Docker Engine 29.8.0; sbx client/daemon 0.48.0, daemon operativo.
- Immagine `docker/sandbox-templates:codex-docker` disponibile e utilizzata;
  template shell disponibile per il test di ciclo di vita della suite.
- Backend configurato: `docker_sandbox`; modello configurato e usato:
  `gpt-5.6-terra`, reasoning `low`.
- Login host ChatGPT disponibile; login proxy sbx verificato con UID `nobody`.
  Nessuna nuova API key, nessun acquisto e nessuna credenziale stampata.
- Skill canoniche DNS e Creation presenti. Integrità dei file canonici verificata.

Il primo tentativo della suite dentro il sandbox dell'agente ha prodotto
212 passed, 1 failed, 2 skipped: il test reale non poteva raggiungere il servizio
Docker login/socket. La riesecuzione autorizzata fuori da quel sandbox ha dato
213 passed, 0 failed, 2 skipped. Il preflight del progetto
`preflight_docker_sandbox()` ha poi restituito `0.48.0`; non è stato necessario
avviare Docker Desktop o il daemon. `sbx --version` non è supportato: la versione
è stata rilevata con il comando corretto `sbx version`.

## Test e conteggi

I conteggi delle categorie si sovrappongono e non vanno sommati. Le righe del
pilota contano casi sperimentali, non test pytest. I 12 sottotest della suite
sono riportati separatamente dal numero dei test principali.

| Categoria | Superati | Falliti | Saltati | Esito |
|---|---:|---:|---:|---|
| Test unitari mirati | 51 | 0 | 0 | 18 Skill Gate + 33 osservazioni |
| Isolamento filesystem | 2 | 0 | 0 | Confronto reale rw/ro e probe ro |
| Docker Sandbox | 2 | 0 | 0 | Gli stessi due test opt-in, cleanup riuscito |
| Verifica Skill | 18 | 0 | 0 | File test_skill_gate.py; include casi negativi e classificazione |
| Codex reale | 2 | 0 | 0 | Un caso positivo e un negativo; 3 turni totali |
| Fase A → Gate → B | 1 | 0 | 0 | Pilota positivo; produzione NOT_RUN |
| Statistiche | 1 | 0 | 0 | Test JSON/CSV/Excel incluso nei 18 test del gate |
| Regressione | 221 | 0 | 2 | Suite finale; ulteriori 12 sottotest superati |

I due skip della suite ordinaria sono esclusivamente i test opt-in
`test_skill_gate_sbx_integration.py` e `test_skill_gate_mount_comparison.py`,
entrambi eseguiti separatamente con `RUN_SBX_ISOLATION_TESTS=1` e superati.
I risultati finali sono conservati nei tre file JUnit
`skill_gate_validation_suite.xml`, `skill_gate_validation_targeted.xml` e
`skill_gate_validation_isolation.xml`. La suite emette tre warning di
deprecazione `pkg_resources`, senza errori.

Comandi eseguiti, dalla radice del repository:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -v tests/test_skill_gate.py tests/test_aut_observation.py \
  --junitxml=reports/skill_gate_validation_targeted.xml
RUN_SBX_ISOLATION_TESTS=1 .venv/bin/python -m pytest -v \
  tests/test_skill_gate_sbx_integration.py tests/test_skill_gate_mount_comparison.py \
  --junitxml=reports/skill_gate_validation_isolation.xml
.venv/bin/python -m pytest -q --junitxml=reports/skill_gate_validation_suite.xml
.venv/bin/python scripts/skill_gate_pilot.py
.venv/bin/python scripts/aggregate_results.py --runs runs \
  --output /private/tmp/tesi-gate-validation-v2-final
```

Sono state eseguite anche compilazione Python dello script, `git diff --check`,
verifica degli header CSV/Excel e confronto degli oggetti Git dei file protetti.
Tutti i test deterministici iniziali, comprese le due integrazioni reali, erano
superati prima del primo turno con modello. Nessun retry del modello: un turno A
positivo, un turno B ripreso e un turno A negativo. Le successive modifiche
riguardano classificazione, metadati, vincoli del verificatore e test; le evidenze
salvate del pilota sono state rivalutate senza richiamare il modello.

## Confronto reale rw/ro

Due Docker Sandbox indipendenti, stesso UID non privilegiato, directory 0777 e
file 0666. Il mount scrivibile usa la sintassi predefinita sbx senza suffisso;
`:rw` non è una sintassi supportata da questa versione. Il mount protetto usa
`:ro`. Il controllo scrivibile prova che non sono i permessi Unix a negare
l'operazione.

Sul mount scrivibile sono riuscite scritture shell/Python, creazione,
eliminazione, modifiche a `lab.conf` e `r1.startup` e scrittura tramite symlink.
Sul mount ro le stesse operazioni sono state negate, così come `chmod`, `chown`
e rimontaggio. Il socket Docker non è utilizzabile dall'utente di prova;
la directory di lavoro separata è scrivibile. SHA-256 del laboratorio ro
invariato e del laboratorio rw cambiato. Nessun mock in queste prove.

## Pilota reale e continuità

Evidenze in `skill_gate_pilot_v2/positive/` e `skill_gate_pilot_v2/negative/`.
Ogni fase conserva separatamente `events.jsonl`, `stderr.log`, prompt e risultato
in `logs/aut/phase_a/` oppure `logs/aut/phase_b/`. Questi log non sostituiscono
quelli storici. Le directory temporanee del laboratorio e dello stato Codex
sono state eliminate; sono conservati eventi, audit, risultati e verdetti.

La documentazione ufficiale descrive `codex exec resume SESSION_ID` per continuare
una sessione non interattiva: [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
L'help delle CLI 0.157.1 e 0.149.1 conferma la disponibilità dell'interfaccia.
La documentazione da sola non è stata trattata come prova del trasferimento.

Il pilota positivo ha persistito lo stato della sessione in una directory di
lavoro temporanea condivisa tra A e B. Ha rimosso il primo sandbox ro e creato un
secondo sandbox rw sullo stesso piccolo laboratorio. Il processo B usa
`exec resume` con l'ID esplicito, senza `--last` e senza `--ephemeral`.
ID A e B coincidono: `01a186e1-3619-71d0-9f0b-293778db9b24`.
Un valore casuale fornito solo nel prompt A è stato scritto correttamente in
`lab.conf` in B; il log B contiene un unico comando `printf` di scrittura e
nessun comando di recupero da file. Il prompt B non contiene quel valore né
il contenuto della Skill. È una prova concreta di continuità per questa
configurazione, non una seconda sessione indipendente dichiarata equivalente.

A ha eseguito un audit mediante un tool shell effettivo e poi un `cat` dedicato
con exit 0 e contenuto integrale della Skill temporanea. Il confronto SHA-256
in `evaluate_read_evidence()` restituisce `evidence_verified`. La rivalutazione
con metadato `skill_protocol=enforced_read_v1` è in `gate_recheck.json`.
Il baseline è rimasto invariato fino all'apertura del gate.

Nel controllo negativo Codex ha eseguito l'audit ma nessuna lettura della Skill;
il verificatore restituisce `verification_failed`, `blocked=true`,
`phase_b_started=false` e `negative_control_passed=true`. Un blocco atteso del
controllo negativo non costituisce un errore del test.

### Sicurezza osservata sul vero Codex

L'audit restituito dal tool include `/proc` del processo Codex antenato,
non soltanto quello del probe deterministico: UID effettivo 65534,
`CapEff=0`, `CapPrm=0`, `CapAmb=0`, `NoNewPrivs=1`. La tabella dei mount mostra
il laboratorio `ro,nosuid,nodev` e la directory di lavoro separata rw.
La scrittura anticipata su `lab.conf` è fallita con `Errno 30: Read-only file system`;
la scrittura in `/etc` con `Permission denied`; il percorso host alternativo
provato non esiste. `sudo -n true` e connessione al socket Docker falliscono.
`codex mcp list --json` non riporta server abilitati dopo l'override del gateway.
Il login proxy funziona con questo stesso utente.

Per rendere osservabile il tentativo reale è stata disattivata la policy interna
Codex, mantenendo l'enforcement esterno tramite UID, no-new-privileges e mount ro.
Non si attribuisce quindi il blocco al solo flag `--sandbox read-only`.

Queste prove non enumerano tutti gli altri socket, servizi di rete, filesystem
e possibili strumenti del template; non verificano ogni possibile percorso
alternativo o configurazione MCP. Gli output dell'audit vengono da un tool
invocato dal modello e non costituiscono un attestatore indipendente completo.
Per questo `validation.json` distingue `probe_outcome` dai
`certification_checks`: l'isolamento completo resta sconosciuto e la
certificazione complessiva del caso positivo è **PARTIALLY_VERIFIED**.

### Consumi osservati

| Caso/fase | Secondi processo | Token input | Token output |
|---|---:|---:|---:|
| Positivo A | 66.0364 | 35416 | 3644 |
| Positivo B | 9.5830 | 32853 | 208 |
| Negativo A | 21.8373 | 22310 | 3604 |

Ogni usage viene da un solo `turn.completed`; input cached incluso nell'input,
non sommato nuovamente. Somma delle due durate positive: 75.6194 secondi di
processo, non tempo totale end-to-end. Overhead e tempo del verificatore del
pilota non sono stati misurati separatamente: rimangono non disponibili, non zero.
Non sono state inserite metriche del pilota nelle 76 run ufficiali.

## Correzioni e compatibilità

- Il verificatore accetta solo fase A; rifiuta esplicitamente B.
- Per `enforced_read_v1` richiede `phase_a/events.jsonl`; non ricade sul log
  storico aggregato. Con artefatti di fase presenti, richiede identità esatta
  tra gli eventi forniti e quelli salvati in A. File mancante, JSON incompleto
  o eventi B scambiati per A bloccano la verifica.
- `observe()` può usare il percorso della traccia A senza richiedere un falso
  log aggregato. Il percorso predefinito storico resta invariato.
- Aggiunta classificazione dei quattro esiti, con valori sconosciuti `None`.
  Nuove metriche: `skill_gate_certification` e
  `skill_gate_context_continuity_verified`. Le run bloccate prima del processo
  riportano `NOT_RUN` e continuità `null`.
- Lo stato del gate viene copiato nel manifest anche quando l'AUT fallisce;
  il test della pipeline verifica manifest e metriche coerenti.
- Aggiunto pilota limitato senza retry, con login esistente, ripresa esplicita,
  log separati e cleanup per entrambe le fasi.

I test coprono letture complete/parziali, hash errati, Skill sbagliate,
nessuna lettura, dichiarazioni non osservate, lettura dopo modifica,
troncamento, timeout, exit errato o mancante, turn fallito, entrambe le Skill,
modifiche osservate e blocco prima di AUT/checker. Aggiunti otto casi pytest
per separazione delle fasi e classificazione. Nessuna aspettativa precedente
è stata indebolita per far passare i test.

Le cinque modalità restano: `no_skill` nessuna Skill; `creation_only` Creation
obbligatoria; `dns_only` DNS obbligatoria; `both_forced` entrambe obbligatorie;
`auto` entrambe disponibili senza lettura imposta. Nessuna modifica ai prompt
funzionali o alle istruzioni DNS. I test di osservazione mantengono distinta la
semantica v1/v2; il selettore di esecuzione preesistente accetta
`explicit_read_v2` e `enforced_read_v1`, non è stata aggiunta un'esecuzione
`explicit_read_v1` che prima non esisteva.

## Statistiche, integrità e limiti residui

Il test sintetico verifica `skill_gate.json`, manifest di pipeline, metriche,
CSV ed Excel, null delle misure non osservabili, conteggio delle run bloccate e
denominatore delle sole run con gate abilitato. I nuovi campi si propagano
attraverso `FIELDS` agli output per-run. Tempi/token reali di un protocollo
integrato di produzione restano **NOT_RUN**; nessuna prova sintetica è presentata
come validazione di questi consumi reali.

L'aggregazione temporanea ha letto 76 run, 32.257 check e 76 gruppi;
header CSV uguali ai corrispondenti fogli Excel Runs, Checks e Summary.
Evidenza: `skill_gate_aggregation_validation.json`. L'output è esclusivamente
in `/private/tmp/tesi-gate-validation-v2-final`.
Confrontati 5.476 file tracciati sotto runs, scenarios, skills, results e prompt
con gli oggetti Git: nessuna variazione. Evidenza: `skill_gate_integrity.json`.
Checker, correction, baseline e 76 run storiche non sono stati modificati.
`sbx ls --json` dopo il pilota e i test ha restituito `[]`.

Per certificare il protocollo completo restano necessari: integrare nel runner
ordinario la macchina a stati sperimentata, rendere indipendente e completa
l'attestazione dell'isolamento per tutti i canali accessibili, registrare i tempi
mancanti, verificare i consumi integrati e completare una run con checker.
Il solo successo del pilota non autorizza a rimuovere `unsupported_backend`:
la protezione di produzione rimane chiusa e **non viene dichiarata completata**.
