# Verifica selettore COST266 — 12 novembre 2026

Checkout: `/Users/matthew/Desktop/Tesi-Skill`, base
`776d89d00973093f021876b3be00ffd84c50835b`, branch `main`, inizialmente pulita.
Nessun commit, push o benchmark a consumo eseguito.

## Mapping e compatibilità

| `--execution-mode` / `--mode` | File predefinito | Protocollo | Strategia interna |
|---|---|---|---|
| `one_shot` | `experiments/cost266.yaml` | `cost266_incremental_continuous_session_v2` | `one_shot` |
| `incremental_isolated` | `experiments/cost266_v1.yaml` | `cost266_incremental_no_feedback_v1` | `incremental` |
| `incremental_continuous` | `experiments/cost266.yaml` | `cost266_incremental_continuous_session_v2` | `incremental` |

Il selettore carica il piano originale corretto prima della pianificazione;
non sostituisce il solo campo protocollo. Un file esplicito incompatibile e
un `--strategy` contraddittorio producono errore prima di AUT o checker.
One-shot v1 rimane disponibile specificando il piano legacy. Senza il nuovo
parametro vengono conservati piano, matrice e filtri della CLI precedente.

Con la selezione esplicita e il piano predefinito, `--skill-mode` può scegliere
anche un trattamento forzato senza riscrivere lo YAML. Un piano esplicito
conserva invece l'elenco delle Skill ammesse. Backend, gate recovery_v1,
retry/fallback e vincoli v1 passano attraverso le validazioni esistenti.

I percorsi delle osservazioni restano originali e i due piani mantengono
experiment_id distinti. Il nuovo `execution_mode` è descrittivo: i manifest
storici senza tale campo vengono verificati e interpretati da protocollo e
strategia, senza riscriverli. Il confronto delle condizioni non viene alterato
per consentire resume storici. Un'etichetta esplicita incoerente è un errore.

## Comandi

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode one_shot
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_isolated
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous
.venv/bin/python scripts/run_cost266.py experiments/cost266_v1.yaml --execution-mode one_shot
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --skill-mode dns_only --prompt-type T1
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --prompt-type T1 --skill-mode no_skill --only-replicate 1 --dry-run
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_isolated --prompt-type T1 --skill-mode no_skill --only-replicate 1 --resume
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --prompt-type T1 --skill-mode no_skill --only-replicate 1 --rerun-correction
```

I comandi senza dry-run avviano il benchmark e richiedono asset coerenti e
l'ambiente funzionante. Non sono stati eseguiti con backend a consumo.

## File modificati

- `scripts/run_cost266.py`: parametro/alias, selezione prima del dataset,
  filtri e descrizione dry-run.
- `benchmark_core/cost266/protocol.py`: nomi delle modalità e derivazione da
  protocollo/strategia.
- `benchmark_core/cost266/runner.py`: campo descrittivo, hash requisiti DNS,
  verifica dell'etichetta, esposizione nelle metriche. Ciclo AUT invariato.
- `benchmark_core/cost266/reports.py`: modalità in CSV/Excel, verifica delle
  condizioni delle coppie e delta nulli per coppie non confrontabili.
- `tests/test_cost266.py`: asserzioni descrittive nel flusso v1 già verificato.
- `docs/COST266_BENCHMARK.md`: guida alle tre modalità e alla compatibilità.

File aggiunti:

- `benchmark_core/cost266/selection.py`: selettore host separato dai motori.
- `benchmark_core/cost266/comparison.py`: controllo esplicito e riutilizzabile
  delle condizioni di confronto, anche tra protocolli.
- `tests/test_cost266_selection.py`: 30 nuovi casi deterministici.
- `docs/COST266_SELECTION_VALIDATION.md`: questo resoconto.

Analizzati e conservati `continuous.py`, `tests/test_cost266_continuous.py` e
i due YAML sperimentali. Conservati anche `benchmark.yaml`, il gate Skill,
il launcher e gli asset COST266 tracciati: confronto byte per byte col commit
base. Le due cartelle `prompt/cost266/{one_shot,incremental}` restano vuote;
il selettore usa il generatore già esistente.

## Test effettivamente eseguiti

Preliminare sui test COST266 esistenti, prima delle modifiche:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_cost266.py tests/test_cost266_continuous.py -k 'not test_real_assets_prepare_deterministic_offline'
```

**74 passati, 1 deselezionato.**

Suite estesa finale, che comprende tutti i nuovi casi e i test COST266 v1/v2,
gate, recovery, report e launcher simulati:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider -k 'not TestDockerSandboxRealShellLifecycle and not test_real_assets_prepare_deterministic_offline and not test_base_resources and not test_experiment_plans_and_prerequisites and not test_historical_reference'
```

**445 passati, 3 saltati, 7 deselezionati, 12 subtest passati in 46,37 secondi.**
I tre warning sono deprecazioni delle dipendenze fs/pkg_resources. Nessuna
dipendenza aggiunta. Compilazione sintattica dei moduli e dei test interessati
tramite `compile()` e `git diff --check` superati.

I 30 casi nuovi coprono mapping, alias, vecchia CLI, argomenti incompatibili,
file espliciti, identità separate, dry-run senza backend, dispatch dei tre
motori, gate dns_only, divieti v1, resume da checkpoint v1 e rifiuto della
ripresa continua distrutta, rivalutazione della sola osservazione selezionata,
manifest/CSV/Excel, etichette storiche senza riscrittura, dataset incoerente e
confronti con controlli discordanti. Le sessioni AUT sono tutte simulate.

Le sette esclusioni corrispondono ai problemi già documentati prima di questa
modifica: tre casi di baseline legacy mancanti, prerequisiti dei piani legacy,
run storica mancante, confronto byte della correction con intestazione e
test del ciclo Docker reale. Dettagli in `COST266_CONTINUOUS_VALIDATION.md`.

Verificata anche la CLI reale con `--help` (exit 0) e con
`--execution-mode incremental_continuous --strategy one_shot --dry-run`
(exit 1, errore esplicito prima del dataset).

## Dry-run e limiti residui

Il dry-run sulla checkout, con `incremental_continuous`, T1 e no_skill,
restituisce ancora exit 1: `Hash dataset non corrispondente: importare in un
nuovo percorso`. Non sono stati cambiati hash, baseline o preparation.json.

Per verificare i piani reali è stato preparato dai sorgenti canonici un dataset
nuovo, in una directory temporanea, mantenendo modello, effort, backend e
percorsi Skill nel config temporaneo. Le quattro invocazioni con T1, replica 1
e dry-run sono terminate con exit 0: one_shot, incremental_isolated,
incremental_continuous e incremental_continuous/dns_only. Le policy stampate
sono rispettivamente un incarico, sessioni indipendenti e sessione persistente
con sandbox condivisa. Nessuna directory runs o results è stata creata.

Directory della verifica:
`/private/var/folders/84/zz92dr1178v8z_tvd_q2dfw40000gn/T/cost266-selector-static-15nynde1`.
Gli hash comuni sono quelli canonici già registrati: baseline
`3a62f9ff9df77ad9b2d24d91862b39f17b07344d9a3548e62c1428d7dadab706`,
correction `bd6de3e9392e8f9c40618fb9d90e81f73a0655b46586f03d02ae4951084a517f`.

Il problema del dataset locale impedisce l'esecuzione completa con gli asset
attuali. Serve un dataset coerente preparato in un nuovo percorso e un piano
esplicito che lo indichi, senza alterare i controlli della baseline corrente.
Non sono stati verificati modello, Docker o Kathara reali. Il collaudo runtime
dei trasporti e le limitazioni informative dei prompt restano quelle già
documentate per v2. Le run v2 incomplete non possono ripartire dopo la
distruzione della sandbox/thread.

I report restano separati per experiment_id. Il controllo di comparabilità
verifica condizioni effettive e requisiti, senza dichiarare equivalenti run
per nome/strategy e senza accorpare automaticamente esperimenti diversi.
Le metriche vengono ancora misurate dai runner originali; il selettore
aggiunge solamente la modalità descrittiva.
