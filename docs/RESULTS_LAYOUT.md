# Separazione dei risultati generali e COST266

`results.directory` in `benchmark.yaml` rimane la radice configurabile. Con la
configurazione predefinita:

```text
results/
  general/_legacy/
  general/<experiment_id>/
  cost266/experiments/<experiment_id>/
  cost266/comparisons/<comparison_id>/
```

Le run sotto `runs/` conservano struttura, manifest, checkpoint, receipt,
correction, baseline, log e metriche originali. I report già presenti al vecchio
percorso non vengono spostati o modificati. L'aggregatore generale esclude le
osservazioni con schema COST266 e il formato COST266 ha profondità distinta;
l'aggregatore COST266 e il confronto selezionano soltanto run COST266.

Per rigenerare offline i report generali dalle run esistenti:

```bash
.venv/bin/python -B scripts/aggregate_results.py
.venv/bin/python -B scripts/aggregate_results.py --experiment thesis_final
.venv/bin/python -B scripts/analyze_results.py --results results/general/thesis_final
```

La prima istruzione pubblica separatamente ogni esperimento generale e, se
presenti, le run legacy. Il nome `_legacy` è riservato alla sezione legacy:
per un esperimento generale già denominato così è necessario un `--output`
esplicito distinto. `--runs`, `--experiment` e `--output` restano disponibili;
`--report-output` e `--results` continuano ad accettare percorsi espliciti.

Per rigenerare un report COST266 senza Codex, Docker o checker:

```bash
.venv/bin/python -B scripts/aggregate_cost266_results.py --experiment cost266
.venv/bin/python -B scripts/aggregate_cost266_results.py --experiment cost266_continuous_v2
```

Il comando accetta `--config` e `--output`; per coerenza con il filtro
dell'aggregatore COST266, l'ultimo componente di un output esplicito deve
coincidere con l'experiment ID. I report generali usano le generazioni atomiche
esistenti. I report COST266 hanno un marker locale con experiment ID e hash dei file generati:
se un report occupato è privo di marker valido o risulta modificato, viene
preservato e l'operazione fallisce. È necessario scegliere una nuova directory
con lo stesso nome esperimento in un'altra radice di output. Un'interruzione
durante la pubblicazione può richiedere una nuova directory, senza sovrascrivere
il report parziale non verificato. Il controllo è ripetuto prima di ogni cella.

Per i confronti, la directory di destinazione deve essere nuova:

```bash
.venv/bin/python -B scripts/compare_cost266.py --comparison-id confronto_v1
.venv/bin/python -B scripts/compare_cost266.py --experiments cost266 cost266_continuous_v2 --output results/cost266/comparisons/confronto_selezionato
```

Il default è `results/cost266/comparisons/comparison`. Con `--comparison-id`
si sceglie un altro ID; `--output` continua a rispettare il percorso esplicito.
I controlli di comparabilità e `usage_verified` non cambiano. Nessun comando di
migrazione automatica modifica i risultati storici: i comandi sopra rigenerano
esclusivamente nuovi report dalle osservazioni conservate.

## Verifiche e file

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_report_paths.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_report_paths.py tests/test_cost266_comparative_report.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider -k 'not TestDockerSandboxRealShellLifecycle and not test_real_assets_prepare_deterministic_offline and not test_base_resources and not test_experiment_plans_and_prerequisites and not test_historical_reference'
```

Rispettivamente **16 test**, **40 test** e **513 test** passati; nella suite
estesa 3 saltati, 7 deselezionati e 12 subtest passati. Le esclusioni sono il
test Docker reale e i sei casi già noti relativi agli asset locali. Le fixture
verificano denominatori separati, più experiment ID, report e run immutati,
destinazioni esplicite, percorso occupato, confronto COST266 e protezione dai
percorsi con `..` verso `runs/`. Nessun modello, Docker o Kathara è stato avviato.

Un esempio delle due sezioni, costruito esclusivamente copiando report prodotti
da fixture indipendenti, è disponibile in
`/Users/matthew/Desktop/Tesi_europa/verifiche/cost266_v15_layout_sintetico`.
Sono dati simulati, non risultati scientifici.

File modificati: `README.md`, `benchmark_core/aggregation.py`,
`benchmark_core/cost266_comparative_report.py` (solo sicurezza del percorso),
`scripts/run_experiment.py`, `scripts/run_benchmark.py`,
`scripts/aggregate_results.py`, `scripts/analyze_results.py`,
`scripts/run_cost266.py`, `scripts/compare_cost266.py`,
`tests/test_cost266_selection.py`, `docs/COST266_BENCHMARK.md` e
`docs/COST266_COMPARATIVE_REPORT.md`.

File aggiunti: `benchmark_core/report_paths.py`,
`scripts/aggregate_cost266_results.py`, `tests/test_report_paths.py` e questa
guida. La modifica ai test esistenti aggiorna le sole aspettative sui percorsi.
I protocolli, la logica di comparabilità, `usage_verified` e la configurazione
`benchmark.yaml` restano invariati. Il dataset COST266 locale continua a
essere bloccato dagli hash incoerenti già documentati.
