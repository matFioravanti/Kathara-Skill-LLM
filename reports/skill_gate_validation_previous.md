# Validazione Skill Gate — 29 ottobre 2026

## Esito

**NON CERTIFICATO.** `enforced_read_v1` non implementa ancora il flusso
A → verifica → B. Per le modalità obbligatorie il runner termina con
`unsupported_backend` prima di avviare l'AUT; non esegue il checker e non
modifica il laboratorio. La valutazione delle evidenze è una funzione separata
e non apre il gate. Non è quindi disponibile un comando per un esperimento
pilota completo sul protocollo.

Codice di partenza: commit `4cbc3f3a92554d37c69c86cc9148a8397fddbc11`;
risultati riferiti a quel commit più le modifiche locali non committate di
questa verifica. Nessuna modifica a prompt, Skill canoniche, correction,
laboratori o 76 run storiche.

## Ambiente

- macOS; Python `.venv` 3.14.6; pytest 9.1.1.
- Codex host 0.157.1; template Codex del sandbox 0.149.1.
- Docker Desktop/server 29.8.0; Docker Sandboxes client e daemon 0.48.0.
- Immagine `docker/sandbox-templates:codex-docker` disponibile; backend
  configurato in `benchmark.yaml`: `docker_sandbox`.
- Login host ChatGPT disponibile; login proxy del sandbox verificato per il
  processo non privilegiato, senza registrare credenziali. Sono presenti le
  Skill canoniche DNS e Creation.
- Le operazioni Docker hanno richiesto l'esecuzione fuori dal sandbox di
  questo agente per accedere ai socket locali.

## Risultati

I conteggi delle categorie si sovrappongono: i test mirati fanno anche parte
della suite completa; non vanno sommati.

| Categoria | Superati | Falliti | Saltati | Esito |
|---|---:|---:|---:|---|
| Test unitari mirati | 43 | 0 | 0 | 10 Skill Gate e 33 osservazioni |
| Isolamento filesystem | 2 | 0 | 0 | Test reali opt-in, inclusa comparazione |
| Docker Sandbox | 2 | 0 | 0 | Stessi due test di isolamento; pulizia verificata |
| Verifica Skill | 10 | 0 | 0 | Test unitari, comprese prove negative |
| Codex reale, lettura | 2 | 0 | 0 | Due turni di prova hanno letto la Skill; non sono test del gate integrato |
| Fase A → Gate → B | 0 | 0 | 1 | NOT_RUN: flusso non implementato |
| Codex reale, tentativo di scrittura osservato | 0 | 0 | 1 | NOT_RUN: nessun comando di scrittura nei log |
| Statistiche | 1 | 0 | 0 | Test sintetico JSON/CSV/Excel; aggregazione storica separata |
| Regressione, suite completa | 213 | 0 | 2 | 12 sottotest superati; due test reali opt-in eseguiti separatamente |

Le due prove opt-in sono saltate nella suite ordinaria perché richiedono
`RUN_SBX_ISOLATION_TESTS=1` e accesso al daemon; entrambe sono state eseguite
a parte e sono passate. La suite completa comprende anche il test reale
preesistente del ciclo di vita Docker Sandbox.

## Comandi eseguiti

```bash
.venv/bin/python -m pytest -v tests/test_skill_gate.py
.venv/bin/python -m pytest -v tests/test_aut_observation.py
RUN_SBX_ISOLATION_TESTS=1 .venv/bin/python -m pytest -v \
  tests/test_skill_gate_sbx_integration.py tests/test_skill_gate_mount_comparison.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/aggregate_results.py --runs runs \
  --output /private/tmp/tesi-gate-validation-results
```

Le prove Docker e la suite completa sono state lanciate con accesso autorizzato
ai socket Docker. Prima della correzione, il nuovo test comparativo è fallito:
`sbx` interpreta `:rw` come parte del percorso. Il test ora usa il mount
scrivibile predefinito senza suffisso e `:ro` per la controparte; è stato
corretto anche il cleanup di sandbox non creati. La successiva esecuzione dei
due test reali ha dato **2 superati, 0 falliti**.

## Confronto mount e sicurezza del processo

Due sandbox indipendenti hanno montato directory con gli stessi permessi Unix,
stesso UID `nobody`, nessuna capability effettiva e `no-new-privileges` attivo.
Sul mount predefinito scrivibile sono riuscite scritture shell e Python,
creazione ed eliminazione, modifiche a `lab.conf` e `r1.startup` e scrittura
tramite link. Sul mount `:ro` le stesse operazioni sono state negate, così come
`chmod`, `chown`, rimontaggio e accesso al socket Docker; la directory di
lavoro separata è rimasta scrivibile. L'hash della directory di sola lettura
è rimasto invariato; quello della directory scrivibile è cambiato.

La prova precedente sul template standard ha mostrato che l'utente `agent`
può usare `sudo` e accedere al socket Docker interno. Il processo Codex del
pilota è stato avviato con `sbx exec -u nobody setpriv --no-new-privs`; il
processo deterministico con gli stessi parametri ha verificato UID, capability,
no-new-privileges, socket, mount e percorsi alternativi. Non è stata ispezionata
separatamente la tabella delle capability del processo Codex mentre era in
esecuzione. Il gateway MCP del template è stato disabilitato tramite override;
`codex mcp list --json` ha riportato server disabilitati. Questo non certifica
tutte le possibili configurazioni MCP o gli altri canali di comunicazione.

## Pilota Codex reale

Laboratorio e Skill di prova sono isolati dagli scenari ufficiali; i loro file
e gli eventi sono in `reports/skill_gate_pilot/`. Il primo avvio con `nobody`
è fallito prima di qualsiasi evento: `Permission denied` inizializzando
l'app-server, perché la directory di stato originale non era scrivibile.
Per la prova successiva è stata creata una home privata nel sandbox e sono
stati predisposti collegamenti interni alla configurazione proxy esistente,
senza copiare o stampare credenziali.

Due successivi turni reali sono terminati con exit 0 e hanno prodotto un
comando dedicato `cat` con exit 0 e contenuto della Skill di prova completo;
`evaluate_read_evidence()` ha confrontato lo SHA-256 e restituito
`evidence_verified`. Il laboratorio è rimasto invariato. I turni hanno riportato
rispettivamente 17.431/363 e 25.987/309 token input/output; non sono metriche
integrate di una run del benchmark.

Entrambi i messaggi finali dell'agente dichiarano che la scrittura iniziale è
stata tentata e negata, ma i corrispondenti eventi non contengono un comando
di scrittura. La dichiarazione non è prova dell'operazione. Il tentativo
Codex reale di scrittura è quindi **non verificato**, non superato. I divieti
di scrittura sopra riportati sono invece prove di processi deterministici.

Non è stata effettuata una fase B con Codex, né un caso negativo end-to-end:
lo Skill Gate del runner è ancora bloccato. Nessun risultato simulato viene
presentato come prova della transizione completa. `sbx ls --json` ha restituito
`[]` dopo la pulizia.

## Verificatore e report

È stato corretto un falso positivo: una lettura shell senza codice di uscita
intero pari a zero non può più verificare il gate. Un `turn.failed` successivo
a `turn.completed` blocca la verifica; una modifica file completata rilevata
nella fase protetta produce `isolation_violation`. Aggiunti test su questi
casi, hash errato e contenuto troncato. Le vecchie metriche storiche non sono
state riscritte.

L'aggregazione in directory temporanea ha letto 76 run, 32.257 check e 76
stati aggregati. Le intestazioni CSV corrispondono ai fogli Excel Runs, Checks
e Summary. Il test sintetico verifica stato, denominatore e valori mancanti;
tempi e token reali delle fasi del gate non sono disponibili perché il flusso
non è implementato, e non sono stati inventati.

## Lavoro rimanente

Implementare e verificare l'orchestrazione che crea la fase A protetta, avvia
Codex con privilegi e strumenti controllati, registra eventi e consumi, applica
il verificatore, controlla il baseline e solo dopo un esito positivo avvia una
fase B scrivibile con cleanup affidabile. Occorre scegliere e verificare una
strategia di contesto: il runner attuale usa `--ephemeral`, quindi non è stata
dimostrata una ripresa della stessa sessione. Occorrono poi il pilota positivo
A → B e quello negativo con verifica insufficiente. Fino ad allora il
comportamento `unsupported_backend` rimane intenzionalmente fail-closed.
