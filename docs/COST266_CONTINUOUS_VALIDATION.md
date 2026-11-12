# Verifica COST266 sessione continua — 12 novembre 2026

Checkout: `/Users/matthew/Desktop/Tesi-Skill`, branch `main`, base
`2f389f4f73d55f32ccba68c3f99f8e3727cb5e10`. Stato iniziale Git pulito.
Nessun commit, push o benchmark a consumo è stato eseguito.

## Implementazione

L'incrementale v2 esegue automaticamente sei turni nel medesimo thread e nella
medesima sandbox scrivibile. Workspace e `.codex/skills` sono predisposti una
volta; ogni checkpoint è uno snapshot host pulito. Il launcher è la classe
`ProtectedCodexSession` già esistente, con verifiche di identità e stdin
aggiuntive nell'adattatore COST266. Nessun fallback verso host o nuovo thread.

`run_recovery_gate` espone un callback scrivibile opzionale e un fornitore del
timeout residuo. In assenza del callback conserva il percorso ordinario, coperto
dai test di regressione. Con v2 il gate gira una volta in sola lettura, conserva
retry/fallback e passa lo stesso thread a un ambiente scrivibile mantenuto per
tutti i sei prompt. La rimozione degli ambienti precede sempre il checker.

Versione: `cost266_incremental_continuous_session_v2`; experiment_id predefinito
`cost266_continuous_v2`. Il v1 conserva identità, comportamento e configurazione
esplicita. Non vengono reinterpretati i risultati storici.

File modificati:

- `benchmark_core/cost266/runner.py`: integrazione sessione, checkpoint,
  verifiche di continuità, resume, metriche per turno e cumulative.
- `benchmark_core/cost266/protocol.py`: versione v2 e validazione backend.
- `benchmark_core/cost266/reports.py`: colonne sessione, gate e checkpoint;
  separazione dei protocolli nei CSV/Excel.
- `benchmark_core/skill_gate.py`: callback opzionale, timeout e classificazione
  dei turni protetti/funzionali senza cambiare il percorso ordinario.
- `experiments/cost266.yaml`: protocollo/id v2, budget invariati.
- `tests/test_cost266.py`: verifica del parsing v2 e del default legacy.

File aggiunti:

- `benchmark_core/cost266/continuous.py`: gestione separata della vita della
  sessione, snapshot, identità, telemetria e cleanup.
- `tests/test_cost266_continuous.py`: casi deterministici v2.
- `experiments/cost266_v1.yaml`: configurazione precedente conservata.
- `docs/COST266_BENCHMARK.md`: guida al protocollo e ai comandi.
- `docs/COST266_CONTINUOUS_VALIDATION.md`: questo resoconto.

Invariati e confrontati col commit base: `benchmark.yaml`, configurazione
Antigravity, `thesis_final.yaml`, launcher Docker, inspect_runner, skill_modes,
workspace, run_metrics e gli input COST266 (baseline, inventario, correction,
preparation). Le due cartelle `prompt/cost266/{one_shot,incremental}` sono vuote.

## Test effettivi

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_cost266_continuous.py tests/test_cost266.py tests/test_skill_gate_recovery.py -k 'not test_real_assets_prepare_deterministic_offline'
```

**131 passati, 1 deselezionato.** Verificati sei turni con un solo workspace,
una sola preparazione Skill e una sandbox scrivibile; stdin limitato al prompt
corrente; persistenza diretta dei file; sei checkpoint senza .codex/correction;
gate unico in tutte le tre modalità forzate; retry/fallback; perdita o assenza
thread, cambio ID sandbox, mancato completamento, errore, timeout, KeyboardInterrupt,
alterazioni Skill/rete/link; cleanup; blocco resume AUT e rivalutazione separata;
one-shot ordinario e recovery; token, cache, reasoning e overhead senza duplicati.
La generazione e l'apertura del workbook con i cinque fogli sono coperte dai test.

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider -k 'not TestDockerSandboxRealShellLifecycle and not test_real_assets_prepare_deterministic_offline and not test_base_resources and not test_experiment_plans_and_prerequisites and not test_historical_reference'
```

**415 passati, 3 saltati, 7 deselezionati, 12 subtest passati.** Ultima esecuzione:
37,17 secondi. I warning sono deprecazioni delle dipendenze fs/pkg_resources.
Compilazione sintattica tramite `compile()` dei moduli interessati e
`git diff --check`: superati. Nessuna dipendenza nuova.

La suite estesa senza escludere i riferimenti legacy ha evidenziato cinque
errori legati ai dati locali: tre casi `test_base_resources`, il caso
`test_experiment_plans_and_prerequisites` e `test_historical_reference`.
Mancano lab.conf delle baseline legacy e la run storica di riferimento.
I relativi moduli/test non sono stati modificati. Il test reale
`TestDockerSandboxRealShellLifecycle` non è stato avviato.

Il test `test_real_assets_prepare_deterministic_offline` falliva già prima
delle modifiche (preliminare: 100 passati, 1 fallito): pretende uguaglianza
byte per byte con la correction conservata, che contiene un'intestazione
aggiuntiva rispetto all'output del generatore.

## Dry-run e problema del dataset attuale

```bash
.venv/bin/python -B scripts/run_cost266.py --dry-run --strategy incremental --prompt-type T1 --skill-mode no_skill
```

Il comando sulla checkout termina correttamente con errore prima di qualsiasi
AUT: `Hash dataset non corrispondente: importare in un nuovo percorso`.
Gli input locali non coincidono con `preparation.json`:

| Artefatto | Hash registrato | Hash effettivo |
|---|---|---|
| lab | `3a62f9ff9df77ad9b2d24d91862b39f17b07344d9a3548e62c1428d7dadab706` | `de8f73356c76e861054850e5f6708e39acce4849f80e1c56725d142613f2a651` |
| correction.yaml | `bd6de3e9392e8f9c40618fb9d90e81f73a0655b46586f03d02ae4951084a517f` | `d589cd9db2dc9670e87318c15058ba980a8f92ddca12dfada8a2077048e67b37` |

L'inventario è coerente. Non sono stati aggiornati gli hash per aggirare il
controllo, né modificati i dati della checkout.

Per verificare il piano completo è stato rigenerato un dataset dai sorgenti
canonici in una directory temporanea risolta, con config temporaneo che conserva
modello, effort e percorsi delle Skill reali. Il dry-run v2 restituisce **exit 0
e 24 osservazioni pianificate**, con gli hash canonici originali comuni alle
due strategie. Nessuna directory runs è stata creata. La directory di verifica
è `/private/var/folders/84/zz92dr1178v8z_tvd_q2dfw40000gn/T/cost266-v2-static-mk33h_2d`.

## Avvio e limiti residui

Dopo aver predisposto un dataset coerente in un nuovo percorso e averlo indicato
nel campo `dataset` di una configurazione sperimentale dedicata:

```bash
.venv/bin/python scripts/run_cost266.py /percorso/esperimento_v2.yaml --prepare
.venv/bin/python scripts/run_cost266.py /percorso/esperimento_v2.yaml --dry-run
.venv/bin/python scripts/run_cost266.py /percorso/esperimento_v2.yaml --strategy incremental --prompt-type T1 --skill-mode no_skill
.venv/bin/python scripts/run_cost266.py /percorso/esperimento_v2.yaml --rerun-correction
```

Il percorso di destinazione non deve esistere prima di prepare. Non riutilizzare
in-place la baseline attuale incoerente. La preparazione usa i sorgenti canonici
della checkout; gli ZIP esterni non sono necessari.

Non sono stati verificati turni modello o il deployment reale Kathara/BIND.
I test provano l'orchestrazione e i controlli con backend deterministici, non
certificano l'ambiente Docker reale. L'ID sandbox deve essere osservabile via sbx;
se manca, il percorso continuo fallisce esplicitamente. La ripresa AUT di una
sessione distrutta è intenzionalmente rifiutata. Le sovrapposizioni informative
già presenti nei sei prompt restano invariate e sono descritte nella guida.

Per le modalità senza gate il percorso continuo usa la classe protetta mentre
lo one-shot conserva il trasporto ordinario: il collaudo delle condizioni runtime
di confronto rimane necessario. Con recovery_v1 entrambi riusano lo stesso
launcher protetto. Nessun risultato scientifico è stato dichiarato a partire
da un test simulato o dal solo dry-run.
