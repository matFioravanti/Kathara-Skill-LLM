# COST266: selezione one-shot, incrementale isolato o continuo

## Politica di validazione incrementale `observe_lab_violations_v3`

La sessione continua mantiene una sola sandbox scrivibile, thread e workspace
per i sei turni funzionali. Solo il prompt corrente viene consegnato via stdin;
i prompt successivi e le correction rimangono sull'host. Ogni turno deve
completarsi prima dello snapshot e del checkpoint che precedono il successivo.
Le modalità forzate possono usare anche un ambiente protetto per il gate Skill:
questo non crea ulteriori sandbox scrivibili per i prompt funzionali.

Le modifiche non autorizzate alla configurazione del laboratorio sono registrate
come `lab_protocol_violations`, senza riparare i file e senza fermare la sequenza.
DNS errato, dichiarazioni mancanti e regressioni statiche non sono criteri di
interruzione. Restano bloccanti perdita del thread o dell'identità sandbox,
timeout, completamento non verificabile, mutazione delle Skill, link simbolici,
artefatti vietati e snapshot non integri. Il checker parte dopo verifica dei
sei checkpoint e cleanup della sandbox, usando le correction originali del dataset.

La politica è registrata nelle condizioni e nella loro fingerprint. Il protocollo
di trasporto v2 resta leggibile per i risultati storici; la nuova politica cambia
esplicitamente le condizioni e impedisce di riprendere con semantica diversa una
run precedente. Usare un nuovo identificativo di esperimento:

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode incremental_continuous --model gpt-6.1-terra --reasoning-effort low --generation-workers 5 --experiment-id cost266_incremental_observe_v3
```

`Runs` e `runs.csv` aggiungono `prompts_sent`, `turns_completed`,
`checkpoints_saved`, `incremental_sequence_completed`, `lab_protocol_violations`
e `static_regressions`. `Stages` conserva violazioni, completamento del turno,
token, tempi e hash di ciascuna fase. Il completamento dei sei turni è separato
dall'esito del checker; i dati storici privi di queste metriche restano vuoti.

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
| `one_shot` | `experiments/cost266_one_shot.yaml` | v2 / `one_shot` | Un prompt completo, percorso originale |
| `incremental_isolated` | `experiments/cost266_v1.yaml` | v1 / `incremental` | Sei sessioni indipendenti, file dal checkpoint precedente |
| `incremental_continuous` | `experiments/cost266.yaml` | v2 / `incremental` | Sei turni, un thread e una sandbox scrivibile |

Tutte terminano con il checker finale. La modalità viene risolta sull'host
prima del dataset, della pianificazione e di qualunque avvio AUT. `--mode`
è un alias di `--execution-mode`. I filtri, resume e rivalutazione restano
disponibili:

Quando il dataset contiene `correction_1.yaml`, `correction_2.yaml`, ecc., il
runner richiede una sequenza numerica senza interruzioni, ne conserva gli hash
e gli snapshot, ed esegue le correction una alla volta sul laboratorio finale.
Il budget `checker_seconds` è complessivo per la sequenza. Ogni run completata
conserva `evaluation/benchmark.xlsx` nella propria cartella sotto `runs/`, con
metriche generali, riepilogo per correction e dettagli dei controlli. I report
CSV e i log individuali rimangono disponibili per verificare la valutazione.
I dataset con la sola `correction.yaml` mantengono il comportamento precedente.

Il piano one-shot predefinito usa solo T1 e le cinque modalità `no_skill`,
`auto`, `dns_only`, `creation_only` e `both_forced`, una ripetizione ciascuna.
Le nuove osservazioni sono separate in `runs/cost266/cost266_one_shot/` e i report in
`results/cost266/experiments/cost266_one_shot/`. Le run degli altri piani
non vengono spostate. Senza `--execution-mode` resta selezionato il piano
storico `cost266.yaml`.

Per eseguire GPT-6.1 Terra con reasoning `xhigh` in un esperimento separato:

```bash
.venv/bin/python scripts/run_cost266.py --execution-mode one_shot --model gpt-6.1-terra --reasoning-effort xhigh --experiment-id cost266_one_shot_terra_xhigh
```

Senza questi parametri restano validi modello ed effort di `benchmark.yaml`.
Riutilizzare lo stesso `--experiment-id` e le stesse opzioni per `--resume` e
`--rerun-correction`; le condizioni sono verificate e non si sovrascrivono run
esistenti con impostazioni differenti. L'effettiva disponibilità del modello e
del livello richiesti dipende dal backend e dall'account.
Con `--execution-mode one_shot` si avviano fino a cinque generazioni in
parallelo. Ogni run passa al checker appena termina la generazione, con un
massimo di cinque checker contemporanei; le correction della singola run restano
sequenziali. Ogni checker usa una copia temporanea con un'identità Kathara
distinta. Il numero di generazioni si può cambiare con `--generation-workers N`;
uno slot di generazione si libera prima dell'attesa o dell'esecuzione del
checker. Le attese sono registrate nel manifest come `generation_queue_seconds`
e `checker_queue_seconds` ed escluse dal budget attivo della run. Il report
aggregato è pubblicato dopo il completamento del gruppo. Il carico e l'isolamento
dei cinque checker concorrenti richiedono verifica sul sistema Kathara utilizzato.

L'avanzamento è stampato in tempo reale e aggiunto a
`logs/cost266/<experiment_id>.log`: ogni riga identifica strategia, prompt,
modalità Skill e ripetizione. Le durate sono misurate con orologio monotono;
la durata della run stampata è quella dell'invocazione corrente, inclusa
l'eventuale attesa del checker, mentre il report è generato successivamente e
ha una durata separata. La validazione statica misura solo la presenza delle
dichiarazioni di zona, non il funzionamento DNS. Il log non contiene i tempi
dei singoli controlli interni del checker.

Come per ogni modifica al codice del protocollo, il fingerprint
`implementation_sha256` cambia: i controlli di integrità possono rifiutare
resume o rivalutazione di run create con una versione diversa. Non modificare
i manifest per aggirare tale controllo.

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
incrementale predefinito mantiene `no_skill` e `auto`. Con `--execution-mode`, senza file sperimentale
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
verificare gli hash del dataset. Il piano one-shot usa la copia rigenerata
`experiments/cost266_one_shot_data_v1`, verificata rispetto ai sorgenti canonici;
la discrepanza documentata continua a riguardare il dataset storico
`experiments/cost266_data`, che rimane invariato.

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
timeout fermano l'esecuzione. Nelle run continue con politica
`observe_lab_violations_v3`, le violazioni della rete vengono registrate e la
sequenza prosegue sul laboratorio prodotto; nelle altre modalità resta il
comportamento storico. Nessuna fase successiva
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

## Percorsi e ripetizioni

Le nuove run COST266 sono salvate in
`runs/cost266/<experiment_id>/<dns_tree_id>/<prompt_type>/<execution_mode>/<skill_mode>/rNNN/`.
Gli identificativi logici e le condizioni rimangono invariati. I percorsi storici
`runs/<experiment_id>/cost266/<dns_tree_id>/cost266/<prompt_type>/<strategy>/<skill_mode>/rNNN/`
sono ancora letti per resume, rivalutazione e report; nessuna run è migrata
automaticamente. Se esistono entrambi i percorsi per la stessa run, il runner
si ferma e l'aggregatore rifiuta il duplicato, lasciando intatti i dati.

`--only-replicate N` seleziona solo N, anche se supera `repetitions` nello YAML;
N deve essere un intero positivo. Senza questa opzione vale `repetitions`.
Questo override vale anche per configurazioni esplicite, che continuano a
vincolare protocolli, strategie, prompt e modalità Skill abilitate. Una run
esistente non viene sovrascritta: usare `--resume` per riprendere o verificare,
`--rerun-correction` per rivalutare, oppure selezionare un'altra ripetizione.
Le verifiche di integrità e delle condizioni restano obbligatorie: modifiche al
codice o alla configurazione possono impedire la ripresa di una run storica.

Le due varianti incrementali devono usare ID esperimento differenti quando
condividono prompt, Skill e ripetizione: l'identificativo logico storico usa
`incremental` per entrambe. Il runner rifiuta il conflitto per evitare ID
ambigui e non altera le run esistenti. Non è prevista una migrazione: per
consultare le run storiche bastano aggregazione e confronto, che leggono
entrambi i layout.
