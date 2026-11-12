# COST266: selezione one-shot, incrementale isolato o continuo

I report COST266 sono pubblicati in `results/cost266/experiments/<experiment_id>/`;
i confronti usano `results/cost266/comparisons/<comparison_id>/`. Le run non
cambiano percorso. Per rigenerazione e sicurezza vedere `RESULTS_LAYOUT.md`.

Implementazione a partire dal commit `2f389f4f73d55f32ccba68c3f99f8e3727cb5e10`.
Il protocollo `cost266_incremental_continuous_session_v2` usa una sola sandbox
scrivibile e un solo thread Codex per i sei turni incrementali. L'esperimento
predefinito ha id `cost266_continuous_v2`, distinto dalle osservazioni v1.
La configurazione precedente è conservata in `experiments/cost266_v1.yaml`.

## Esecuzione

Dalla checkout, dopo aver verificato asset e prerequisiti:

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode one_shot
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_isolated
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous
```

| Modalità | Configurazione predefinita | Protocollo / strategia | Richieste funzionali |
|---|---|---|---|
| `one_shot` | `experiments/cost266.yaml` | v2 / `one_shot` | Un prompt completo, percorso originale |
| `incremental_isolated` | `experiments/cost266_v1.yaml` | v1 / `incremental` | Sei sessioni indipendenti, file dal checkpoint precedente |
| `incremental_continuous` | `experiments/cost266.yaml` | v2 / `incremental` | Sei turni, un thread e una sandbox scrivibile |

Tutte terminano con il checker finale. La modalità viene risolta sull'host
prima del dataset, della pianificazione e di qualunque avvio AUT. `--mode`
è un alias di `--execution-mode`. I filtri, resume e rivalutazione restano
disponibili:

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --prompt-type T1 --skill-mode auto --only-replicate 1 --dry-run
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_isolated --prompt-type T1 --skill-mode no_skill --only-replicate 1 --resume
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --prompt-type T1 --skill-mode no_skill --only-replicate 1 --rerun-correction
.venv/bin/python scripts/run_cost266.py experiments/cost266_v1.yaml --execution-mode one_shot --dry-run
```

L'ultimo comando mantiene one-shot v1 per il confronto con l'incrementale
isolato. Un file esplicito incompatibile viene rifiutato: il selettore non ne
sostituisce protocollo, dataset o experiment_id. Anche una combinazione come
`--execution-mode incremental_continuous --strategy one_shot` è un errore.
Senza il nuovo parametro valgono la configurazione e la matrice precedenti,
compreso il vecchio filtro `--strategy`:

```bash
.venv/bin/python scripts/run_cost266.py --dry-run
.venv/bin/python scripts/run_cost266.py --strategy incremental --prompt-type T1 --skill-mode no_skill
.venv/bin/python scripts/run_cost266.py --strategy one_shot --prompt-type T1 --skill-mode no_skill
.venv/bin/python scripts/run_cost266.py --resume --dry-run
.venv/bin/python scripts/run_cost266.py --rerun-correction
```

Solo dry-run, preparazione offline e test deterministici sono stati eseguiti
durante lo sviluppo. Gli altri comandi avviano AUT e checker, consumano token
e richiedono l'ambiente Docker/Kathara funzionante.

`benchmark.yaml` conserva agente, modello, effort, Skill e backend attivi.
Non vengono modificati autenticazione, policy di rete o memorie. Il piano
mantiene `no_skill` e `auto`. Con `--execution-mode`, senza file sperimentale
esplicito, `--skill-mode` seleziona il trattamento richiesto anche per una Skill
forzata. Non viene riscritto lo YAML. Con un file esplicito, la Skill richiesta
deve essere inclusa in `skill_modes`; senza `--execution-mode` il parametro
conserva il comportamento storico di filtro della matrice.
La v2 supporta anche `dns_only`, `creation_only`, `both_forced` con il gate
`enforced_read_v1/recovery_v1` originale. Le combinazioni non supportate falliscono
prima dell'AUT; l'incrementale v2 richiede Codex e `docker_sandbox`.

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --skill-mode dns_only --prompt-type T1
```

Il gate originale conserva retry, fallback e sandbox protetta. L'incrementale
isolato conserva il rifiuto delle Skill forzate con recovery_v1. I percorsi
delle Skill in `benchmark.yaml` non vengono modificati.

Il dry-run stampa modalità, protocollo, experiment_id, prompt type, Skill,
ripetizione, numero di turni, policy di sessione/sandbox e checker finale.
Non avvia Codex, Docker o Kathara e non crea osservazioni. Continua però a
verificare gli hash del dataset: la discrepanza locale già documentata blocca
anche il dry-run. Test e verifica del selettore usano dataset temporanei
coerenti; baseline e `preparation.json` della checkout restano invariati.

## Ciclo di vita

1. Il runner alloca baseline, correction e prompt sull'host.
2. `ContinuousAutSession` copia una volta il lab in una directory temporanea
   isolata e prepara una volta `.codex/skills`.
3. Senza gate obbligatorio viene creata direttamente la sandbox scrivibile.
4. Con recovery_v1 viene eseguito il gate originale in sola lettura, compresi
   retry/fallback e verifica dei byte. Il callback `writable_phase(session)`
   consente poi di usare la stessa sandbox scrivibile per tutti i turni DNS.
5. Il primo turno funzionale crea un thread, oppure riprende quello del gate.
   I successivi usano `codex exec resume <thread_id>`.
6. Ogni turno deve terminare senza errore/timeout e contenere un thread valido,
   un solo `turn.completed` e nessun `turn.failed` o errore bloccante. Nome e ID
   della sandbox, thread e bundle Skill sono verificati prima/dopo i turni.
7. Il laboratorio corrente viene copiato in snapshot host puliti; `.codex`
   rimane nel workspace vivo e non entra nei checkpoint o nel checker.
8. Dopo il sesto turno la sandbox viene rimossa e il cleanup verificato.
   Solo allora viene chiamato il checker finale, una volta, con l'oracle comune.

`ProtectedCodexSession` mantiene gli stessi probe di privilegi, mount, MCP,
login e rete già utilizzati dal gate. Non è stata introdotta una seconda
implementazione di launcher o autenticazione. Lo one-shot continua a usare
`run_aut`: un solo compito funzionale e il checker finale originali. La v2
conta separatamente eventuali turni di lettura Skill anche per lo one-shot.
Nelle modalità senza gate il trasporto continuo usa i probe della classe
protetta; il confronto runtime con il trasporto ordinario one-shot richiede
ancora un collaudo reale, oltre ai test simulati.

Un'esecuzione senza gate crea una sandbox scrivibile. Con gate vengono creati
due ambienti sequenziali: uno protetto e uno scrivibile; il thread resta unico.
Le sei fasi non creano sei sandbox. Le memorie automatiche rimangono disabilitate:
la continuità deriva dal thread esplicitamente ripreso e dallo stato temporaneo.

## Prompt e isolamento informativo

Le sei stringhe funzionali conservano i byte e la semantica del generatore
esistente. Il runner invia solo il prompt corrente su stdin, senza concatenare
la conversazione e senza esportare i prompt futuri, l'inventario completo,
correction, report o log dell'host nel workspace dell'AUT. La conversazione
precedente è conservata dal thread Codex. Non viene fornito feedback del checker.

Le cartelle `prompt/cost266/one_shot` e `prompt/cost266/incremental` restano
inalterate: il loro caricamento non fa parte di questa modifica. La CLI continua
a usare il generatore in `protocol.py`.

Limite ereditato: gli oggetti zona del generatore includono `records`; alcuni
record cittadini sono già presenti nella fase 4 e ribaditi nella fase 5. Questa
sovrapposizione non viene riscritta, come richiesto dalla conservazione dei sei
prompt. L'isolamento della nuova esecuzione impedisce accesso ai *prompt futuri*;
non modifica le informazioni già contenute nel prompt corrente.

## Checkpoint, errori e ripresa

I percorsi `steps/01/checkpoint` ... `steps/06/checkpoint` sono snapshot host,
non nuovi workspace AUT. Ogni fase conserva in `steps/NN/attempts/001/` prompt,
eventi, result, `.eval`, diff, validazione statica, hash, dimensione e metadata
di sessione. Le receipt e gli hash già esistenti restano verificati.

I controlli intermedi verificano invarianti e dichiarazioni di zona: non sono
test semantici BIND. Restano fuori dal contesto dell'agente e non riparano file.
Errori infrastrutturali, perdita di thread/ID, modifica di Skill, stdin alterato,
timeout e violazioni della rete fermano l'esecuzione. Nessuna fase successiva
viene inviata, nessuno stato parziale è promosso e il checker finale non parte.
Il cleanup è eseguito anche per KeyboardInterrupt. I checkpoint precedenti e
i log del tentativo fallito rimangono disponibili sull'host.

I limiti restano 900 secondi per turno, 9000 secondi totali attivi, 1800 per
checker. Il gate usa lo stesso limite per turno e il residuo del budget totale.
Setup/cleanup ereditati hanno limiti propri e possono eccedere una deadline;
lo sforamento interrompe la run e viene misurato, senza interrompere il cleanup.

**La ripresa AUT di una v2 incompleta viene rifiutata.** Il cleanup distrugge la
sandbox e la directory temporanea di stato; un checkpoint non può dimostrare
continuità della conversazione. Serve una nuova osservazione, per esempio un
nuovo experiment_id o una nuova ripetizione pianificata. Non viene creato un
thread sostitutivo né ricostruito il contesto da un elenco di vecchi prompt.

Se tutti i turni sono conclusi e il cleanup è verificato, si può riprendere
solo il checker fallito oppure usare `--rerun-correction`. Una run COMPLETED
viene saltata da resume. Un cleanup non verificato blocca anche il rerun.
Il comportamento v1 rimane disponibile tramite il suo protocollo esplicito;
gli hash impediscono di reinterpretare vecchie osservazioni come v2.

## Metriche e compatibilità

CSV/Excel conservano le colonne storiche e aggiungono protocollo, thread,
sandbox, continuità, conteggi di ambienti protetti/scrivibili, turni funzionali
e gate, tempi e token separati. Le fasi includono hash/dimensione checkpoint,
token cached/reasoning, numero chiamate e stato del turno.

Il campo `execution_mode` compare nei manifest nuovi, nelle metriche e nei
fogli Runs, Checks, Summary e Stages. Per le run storiche è ricavato da
protocollo e strategia senza riscrivere i manifest. Identificativi e directory
restano quelli esistenti: i piani predefiniti v1/v2 hanno experiment_id distinti.
Un'etichetta esplicita incoerente viene rifiutata anche durante resume.

Con Codex Docker Sandbox 0.165.0, verificato nei controlli reali, i contatori
`turn.completed.usage` sono cumulativi del thread anche dopo resume. Il runner
conserva eventi e result originali e salva in `usage_accounting.json` gli
incrementi fra contatori successivi dello stesso thread. Gate, retry, fallback
e turni funzionali sono normalizzati in ordine prima di essere separati.
I totali sommano questi incrementi; reasoning e cache restano sottoinsiemi.
Valori non ricostruibili rimangono null con una diagnosi. I consumi osservati
dei tentativi falliti sono inclusi; l'overhead resta misurato una volta per
sessione. CSV/Excel espongono `usage_semantics` e `usage_verified`.

Le osservazioni storiche non vengono riscritte automaticamente e restano
esplicitamente non certificate per i token finché non vengono ricalcolate.
Il comando offline `scripts/recalculate_cost266_tokens.py` produce nuovi JSON,
CSV, Excel e log Inspect in una cartella esterna nuova, con copie dei risultati
precedenti e hash delle sorgenti. Procedura, test e limiti:
[`COST266_TOKEN_ACCOUNTING.md`](COST266_TOKEN_ACCOUNTING.md).

Il gate conserva anche `phase_b` come copia host delle evidenze della prima
scrittura: il verificatore recovery_v1 esistente può così verificare la
consegna delle Skill prima del lavoro. Questa copia non è un turno aggiuntivo
e non viene sommata di nuovo. Le sei directory di turno contengono le evidenze
originali; i log Inspect del gate sono conservati separatamente.

Reports e statistiche distinguono protocolli v1/v2. Il foglio Pairs verifica
baseline, correction, inventario, requisiti DNS, prompt type, modello, effort,
Skill/bundle, budget, configurazione e versioni dei componenti prima di
calcolare differenze. Le coppie incompatibili riportano la causa e delta nulli.
Per i requisiti storici senza hash dedicato servono inventario e hash
dell'implementazione identici; altrimenti il confronto resta non verificabile.
Il controllo è riutilizzabile per confronti v1/v2 espliciti; i report standard
restano separati per experiment_id e non accorpano automaticamente esperimenti.
La conformità dei manifest non prova l'equivalenza runtime dei trasporti:
rimane necessario il collaudo reale già descritto sopra.
Non è stato eseguito un benchmark a consumo. Verifiche del selettore:
`COST266_SELECTION_VALIDATION.md`. Dettagli v2 e problema del dataset locale:
`COST266_CONTINUOUS_VALIDATION.md`.
