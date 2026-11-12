# COST266 — token cumulativi, correzione e ricalcolo

Checkout `/Users/matthew/Desktop/Tesi-Skill`, base
`776d89d00973093f021876b3be00ffd84c50835b`. Le modifiche locali del selettore
già presenti sono state preservate: nessun reset, commit o push.

## Base empirica

I controlli reali del 12 novembre 2026 hanno verificato che, con Codex CLI
0.165.0 nel backend Docker Sandbox, `turn.completed.usage` coincide con
`total_token_usage` del thread. Non rappresenta il solo consumo della nuova
invocazione `exec resume`. Le somme precedenti duplicavano i turni precedenti.
Questo risultato corregge l'assunzione sui token del primo resoconto v2.

Evidenze originali, conservate:
`/Users/matthew/Desktop/Tesi_europa/verifiche/cost266_reale_20261112`.
Il probe `token_counter` comprende sia i JSONL dei turni sia il file di stato
Codex con `session_meta.cli_version`, identità del thread e token_count.
Per questa correzione non sono state effettuate nuove chiamate al modello.

## Algoritmo

`UsageLedger` mantiene stati separati per thread e per campo. Ogni incremento
è `current_cumulative - previous_cumulative`. Lo zero iniziale è ammesso solo
con identità del thread verificata e prova di una nuova esecuzione; il solo
evento `thread.started` non prova che il thread sia nuovo.

L'invocazione originale distingue `exec` da `exec resume` e, per il launcher
protetto, registra `session_expected`. Un cambiamento incompatibile non
inizializza arbitrariamente un nuovo stato e non aggira i controlli di
continuità del protocollo. Creare un'altra sandbox non azzera il ledger.

I campi sono input, output, cached input, reasoning output, cache write input
e totale dichiarato. Sono differenziati separatamente. La somma input+output
è `total_calculated`; il provider conserva `total_reported`. Cache e reasoning
non vengono aggiunti nuovamente al totale.

La regola automatica cumulativa è limitata alla combinazione empiricamente
verificata Codex / docker_sandbox / 0.165.0. Un runtime numerico non riconosciuto
produce contatori derivati nulli e un esito non verificato. I backend con uso
per turno non ricevono sottrazioni tra invocazioni. I flussi legacy senza una
versione runtime concreta restano leggibili, con `legacy_unverified`, senza
essere dichiarati normalizzati.

## Evidenze e anomalie

Gli `usage` originali nei JSONL e nei result dei singoli turni restano intatti.
Il file aggiunto `usage_accounting.json` contiene:

- `usage_raw`, `usage_delta`, `usage_semantics`, `usage_verified`;
- identità, versione runtime, stato di completamento o fallimento;
- diagnosi per campo, stato della storia e hash delle sorgenti ordinate.

Gli hash legano il risultato derivato anche ai turni precedenti. Letture
successive rilevano modifiche delle evidenze e restituiscono valori sconosciuti.
I sidecar dei turni già conclusi sono deterministici: il proseguimento non
modifica i byte protetti dalle receipt delle fasi precedenti.

Campi mancanti, null, booleani, stringhe, numeri negativi o non interi non
diventano zero. Un contatore decrescente produce null e una diagnosi, senza
creare incrementi negativi. Una lacuna rende sconosciuto l'incremento che
attraversa la lacuna; un nuovo valore valido può ancorare i turni successivi,
ma non rende completo il totale precedente. Una regressione nello stesso
thread resta incoerente finché non esiste una nuova identità verificata.

I tentativi falliti mantengono gli utilizzi effettivamente osservati, anche
quando disponibili nel solo evento fallito. Non vengono inventati i consumi
di chiamate interrotte senza contatori. Se Inspect non può rappresentare
input/output sconosciuti, il blocco `model_usage` è omesso: i null e le diagnosi
rimangono nei metadata, anziché essere trasformati in zero.

## Gate e aggregazione

Tutta la sequenza dello stesso thread è normalizzata prima della separazione
fra lettura iniziale, retry, fallback e lavoro funzionale. Vale sia per il
continuo sia per il gate nel percorso AUT ordinario one-shot.

`run_recovery_gate` usa gli incrementi per le somme protette/scrivibili. Il
suo vecchio aggregate `result.usage` resta una rappresentazione grezza di
compatibilità; le metriche e Inspect usano il sidecar derivato. `collect_metrics`
somma le fasi corrette e le sole letture protette. `phase_b`, quando è una copia
del primo turno funzionale continuo, rimane evidenza e non viene risommata.

Metriche JSON, CSV, Excel e Inspect riportano gli stessi incrementi. I report
aggiungono `usage_semantics` e `usage_verified`; le righe storiche senza
contabilizzazione verificata sono etichettate come tali. Non vengono calcolati
delta di token fra coppie con contabilizzazione non verificata. Tempi,
checkpoint, turni, sandbox, gate e risultati checker conservano i loro percorsi
di misura originali.

## Dimostrazione a due turni

| Contatore | Primo cumulativo / incremento | Secondo cumulativo | Incremento secondo turno | Totale |
|---|---:|---:|---:|---:|
| Input | 11.363 | 22.751 | 11.388 | 22.751 |
| Output | 5 | 10 | 5 | 10 |
| Cached input | 9.088 | 20.224 | 11.136 | 20.224 |

Il totale è il contatore finale, non la somma 11.363+22.751. Il caso è
coperto dai test e dal ricalcolo offline del probe reale.

## Ricalcolo esplicito

Dalla checkout:

```bash
.venv/bin/python -B scripts/recalculate_cost266_tokens.py \
  /percorso/canonico/run_originale \
  --output /percorso/canonico/export_nuovo
```

Sorgente e output devono essere percorsi canonici senza symlink. L'output
deve essere nuovo ed esterno alla sorgente. Nessuna chiamata Codex, Docker
o checker viene avviata. Per una run COST266 vengono verificate prima le
receipt e le evidenze originali, usando le condizioni conservate.

Il comando ricostruisce l'ordine strutturale di gate/retry/fallback e fasi,
verifica la nuova identità o il resume e mantiene un ledger per thread.
Esclude i compatibility stream, le copie `logs/aut` dei figli `turn` e
`phase_b` solo quando è dimostrata la corrispondenza con il primo turno.
Lacune di fase o retry dichiarati mancanti restano diagnosticate.

La versione deve provenire da runtime metadata o da un `session_meta` Codex
legato all'esatto thread. `--codex-version 0.165.0` è soltanto un controllo
del valore atteso: non fornisce da solo la prova della versione storica e
non sovrascrive prove discordanti.

L'export contiene:

- `recalculation_manifest.json`: hash delle sorgenti prima/dopo, versioni,
  alias esclusi, diagnosi e stato di verificabilità;
- `previous_results/`: copie byte per byte dei risultati JSON, CSV/Excel e
  log Inspect precedenti disponibili nella sorgente;
- `normalized/`: accounting, metriche per turno e nuovi log Inspect;
- `recalculated_metrics.json`, `turns.csv`, `totals.csv`, `benchmark.xlsx`:
  nuovi aggregati e contatori per thread/categoria.

Exit code: 0 per un ricalcolo verificato, 2 per un export con dati non
ricostruibili, 1 per errore di input/integrità. L'export non è una nuova run
AUT e non sostituisce directory o receipt da usare con resume.

## Ricalcolo delle evidenze reali già eseguito

Output:
`/Users/matthew/Desktop/Tesi_europa/verifiche/cost266_token_ricalcolo_20261112`.

| Sorgente | Turni | Input corretto | Output corretto |
|---|---:|---:|---:|
| ordinary_one_shot | 1 | 22.760 | 110 |
| ordinary_incremental_isolated | 6 | 135.885 | 682 |
| continuous_no_skill | 6 | 149.911 | 1.147 |
| continuous_dns_only_retry | 7, incluso gate | 210.055 | 836 |
| token_counter, export verified_state | 2 | 22.751 | 10 |

Tutti dichiarano sorgenti invariate. Il caso a due turni è verificato anche
dai metadata originali della sessione, senza una versione imposta. Nel continuo
senza Skill il vecchio totale input era 516.878; nel continuo con gate era
814.708. I nuovi totali coincidono con gli ultimi contatori dei thread.

Nel gate reale: 24.817 input e 155 output per la lettura protetta;
185.238 input e 681 output per i sei turni funzionali. Le somme sono
210.055 e 836. La copia phase_b non aggiunge alcun consumo.

## Test e file

Test deterministici dedicati, senza modelli o Docker:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_token_accounting.py tests/test_token_recalculation.py
```

**28 casi dedicati verificati nella suite finale.** Coprono il caso empirico,
sei turni, sei thread indipendenti,
contatori per turno, tutti i campi, totale provider distinto, errori/null,
regressioni, thread sostitutivi, runtime non verificati, consumi parziali,
gate diretto/retry/fallback e sei turni, gate one-shot, receipt, resume,
rerun-correction, CSV/Excel/Inspect, ricalcolo immutabile e metadata storici.

La suite estesa finale usa le stesse esclusioni preesistenti:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider -k 'not TestDockerSandboxRealShellLifecycle and not test_real_assets_prepare_deterministic_offline and not test_base_resources and not test_experiment_plans_and_prerequisites and not test_historical_reference'
```

**473 passati, 3 saltati, 7 deselezionati, 12 subtest passati in 52,11 secondi;
nessun test fallito nella suite finale.** Compilazione sintattica e
`git diff --check` superati. Le sette esclusioni
sono il test Docker reale e i sei casi già noti relativi a dati locali,
baseline legacy e riferimento storico mancanti. I tre warning fs/pkg_resources
sono deprecazioni delle dipendenze.

File modificati da questa correzione:

- `benchmark_core/run_metrics.py`: consumo dei valori derivati e diagnosi;
- `benchmark_core/cost266/runner.py`: aggregazione e separazione gate;
- `benchmark_core/cost266/continuous.py`: accounting dei turni e del gate;
- `benchmark_core/skill_gate.py`: somme normalizzate lungo l'intera sequenza;
- `benchmark_core/docker_sandbox_runner.py`: sidecar e versione del turno;
- `benchmark_core/cost266/reports.py`: verificabilità e totali espliciti;
- `benchmark_core/inspect_adapter.py`: metriche normalizzate, null e output separato;
- `docs/COST266_BENCHMARK.md`: guida aggiornata.

File aggiunti:

- `benchmark_core/token_usage.py`;
- `benchmark_core/token_recalculation.py`;
- `scripts/recalculate_cost266_tokens.py`;
- `tests/test_token_accounting.py`;
- `tests/test_token_recalculation.py`;
- `docs/COST266_TOKEN_ACCOUNTING.md`.

## Limiti residui

Gli incrementi sono certificabili solo per semantiche e identità runtime
verificate e con una storia sufficiente. Altre versioni richiedono una nuova
verifica empirica; contatori perduti non vengono ricostruiti arbitrariamente.
Gli export storici non diventano implicitamente osservazioni valide.

Resta il problema separato degli hash del dataset COST266 locale: il loader
continua a rifiutarlo. Baseline, correction, inventory, preparation.json,
protocollo DNS, prompt sperimentali, modello, effort, autenticazione e
isolamento non sono stati modificati. Le cartelle dei prompt restano vuote.
Non è stato eseguito un nuovo benchmark completo o a consumo per questa patch.
