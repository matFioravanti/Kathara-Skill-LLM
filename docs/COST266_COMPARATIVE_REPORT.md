# Confronto automatico COST266 v1.4

Il comando legge le osservazioni COST266 già presenti in `runs/` e scrive un
report separato. Non esegue AUT, Docker, Kathara, checker o ricalcoli token.

```bash
.venv/bin/python -B scripts/compare_cost266.py
.venv/bin/python -B scripts/compare_cost266.py --experiments cost266 cost266_continuous_v2 --output results/cost266/comparisons/confronto_v1
```

Senza `--output` la destinazione è `results/cost266/comparisons/comparison`;
`--comparison-id` sceglie un altro nome. L'output deve essere una directory
nuova, fuori da `runs/` ed `experiments/`.
`--root /percorso/canonico` consente di analizzare un'altra radice contenente
`runs/`. I nomi esperimento non sono fissi. Se la scoperta automatica non trova
osservazioni, produce report vuoti con intestazioni; un esperimento richiesto
esplicitamente senza osservazioni produce errore. Non vengono create run.

La chiave di accoppiamento è scenario, albero DNS, livello del compito,
prompt type, modalità Skill e replica. `experiment_id` e modalità non entrano
nella chiave. Una one-shot v1 resta nell'elenco delle osservazioni come legacy;
non viene sostituita né fusa con la one-shot v2. Duplicati della stessa chiave
e modalità sono segnalati e non viene scelto un candidato arbitrario.

Prima del confronto vengono verificati identità, condizioni, baseline,
correction, receipt, artefatti, checkpoint e risultati checker tramite i
verificatori esistenti. `comparison_mismatches` verifica baseline, correction,
inventario, requisiti DNS, modello, effort, agente, Skill, bundle, protocollo
Skill, budget, configurazione e versioni componenti. Per requisiti storici
senza hash dedicato si usa soltanto il fallback esistente con inventario e
impronta implementazione coincidenti. I protocolli v1/v2 sono il trattamento.
Anche l'impronta dell'implementazione deve essere presente e coincidere: questo
criterio conservativo evita di mescolare versioni del codice non verificabili.
Anche backend e versione effettiva dell'agente, rilevata nelle metriche delle
fasi, devono essere presenti e coincidere; se mancano il confronto è
contrassegnato come non verificabile.

La convenzione è **delta = B − A**: un delta positivo sul pass rate indica
che B supera A; un delta negativo su token o tempo indica un valore minore
per B. Un risultato su una metrica non dimostra un miglioramento generale.
Il pass rate è espresso fra 0 e 1: un delta di 0,10 equivale a 10 punti
percentuali.
Run incomplete, checker non disponibile, anomalie di integrità, condizioni
diverse e duplicati non producono delta confrontabili. Una run con checker
eseguito e task fallito rimane visibile con il risultato effettivo.

I token sono inclusi solo con `usage_verified` e aggregato coerente con le
evidenze delle fasi; altrimenti sono nulli, con motivazione. Non si sommano
contatori cumulativi grezzi, reasoning o cache ai rispettivi totali. Per le
run storiche il ricalcolo offline resta esplicito e non viene applicato alle
sorgenti dal confronto; gli export separati non sono importati automaticamente.

L'output contiene `observations.csv`, `pairwise_comparisons.csv`,
`three_modes_comparison.csv`, `summary.csv`, `benchmark_comparison.xlsx` e
`comparison_manifest.json`. Excel comprende Observations, Pairwise, Three
Modes, Summary e Diagnostics. Il manifest registra le sorgenti, revisioni,
hash dei file, chiavi, algoritmo, conteggi e motivi di esclusione. Le statistiche
sono separate anche per impronta delle condizioni e indicano numerosità valide
ed escluse; la deviazione standard è disponibile soltanto con almeno due valori.
Ogni riepilogo per prompt e/o Skill mantiene anche la modalità di esecuzione,
così le statistiche non mescolano i trattamenti.
Le osservazioni singole valide contribuiscono al proprio gruppo di condizioni,
anche quando non esiste una coppia; i duplicati non vengono selezionati.
Per gli indicatori booleani la media è la frazione di valori veri osservati;
un valore mancante non viene contato come falso.
Non viene affermata significatività statistica.

## Dataset locale

Il dataset corrente è incoerente con `preparation.json` e il controllo rimane
attivo. Per predisporre un nuovo dataset, creare una copia del piano sperimentale
in cui `dataset` indichi un **nuovo** percorso sotto `experiments/`, poi usare:

```bash
.venv/bin/python -B scripts/run_cost266.py /percorso/piano_nuovo.yaml --prepare
.venv/bin/python -B scripts/run_cost266.py /percorso/piano_nuovo.yaml --dry-run
```

Il percorso dataset di destinazione non deve già esistere. La preparazione usa
i sorgenti previsti dal progetto; non modificare baseline o hash del dataset
esistente. Questa procedura è documentata e non è stata eseguita per il report.

## Verifiche eseguite

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_cost266_comparative_report.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider -k 'not TestDockerSandboxRealShellLifecycle and not test_real_assets_prepare_deterministic_offline and not test_base_resources and not test_experiment_plans_and_prerequisites and not test_historical_reference'
```

I **24 test dedicati sono passati** sulla versione finale. La suite estesa ha
restituito **496 passati, 3 saltati, 7 deselezionati e 12 subtest passati**;
successivamente sono stati affinati alcuni controlli di completezza e valori,
verificati nuovamente con tutti i test dedicati. Le esclusioni riguardano il
test Docker reale e i sei casi già documentati per asset e riferimenti locali.

Il comando CLI è stato eseguito anche su tre osservazioni di fixture: tre
coppie e una terna verificabili, con hash identici delle run e dei report
sorgente prima e dopo. L'esempio è in
`/Users/matthew/Desktop/Tesi_europa/verifiche/cost266_v14_confronto_fixture_verificato`:
sono dati simulati, non risultati scientifici.

File aggiunti: `benchmark_core/cost266_comparative_report.py`,
`scripts/compare_cost266.py`, `tests/test_cost266_comparative_report.py` e
questa guida. Il modulo riusa `comparison_mismatches` e i verificatori delle
run esistenti; rimane fuori dalla cartella `cost266/` affinché la sua presenza
non cambi l'impronta dell'implementazione usata dalle condizioni di resume.
Nessuna run sorgente, protocollo, file dei prompt, dato baseline o codice di
contabilizzazione token è stato modificato. Nessuna chiamata a consumo o
benchmark reale è stato avviato.
