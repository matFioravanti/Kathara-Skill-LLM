# COST266: sessione incrementale continua v2

Implementazione a partire dal commit `2f389f4f73d55f32ccba68c3f99f8e3727cb5e10`.
Il protocollo `cost266_incremental_continuous_session_v2` usa una sola sandbox
scrivibile e un solo thread Codex per i sei turni incrementali. L'esperimento
predefinito ha id `cost266_continuous_v2`, distinto dalle osservazioni v1.
La configurazione precedente è conservata in `experiments/cost266_v1.yaml`.

## Esecuzione

Dalla checkout, dopo aver verificato asset e prerequisiti:

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
mantiene `no_skill` e `auto`; per pianificare le altre modalità aggiungerle
esplicitamente a `skill_modes` in una configurazione sperimentale dedicata.
La v2 supporta anche `dns_only`, `creation_only`, `both_forced` con il gate
`enforced_read_v1/recovery_v1` originale. Le combinazioni non supportate falliscono
prima dell'AUT; l'incrementale v2 richiede Codex e `docker_sandbox`.

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

I token sono letti dal singolo turno. Il totale somma i sei utilizzi funzionali
più i turni protetti/retry/fallback, senza usare l'ultimo evento della
conversazione come totale e senza sommare reasoning o cache una seconda volta.
Valori non osservati rimangono null. I costi dei tentativi falliti sono inclusi.
L'overhead della sandbox è conteggiato una volta a livello sessione.

Il gate conserva anche `phase_b` come copia host delle evidenze della prima
scrittura: il verificatore recovery_v1 esistente può così verificare la
consegna delle Skill prima del lavoro. Questa copia non è un turno aggiuntivo
e non viene sommata di nuovo. Le sei directory di turno contengono le evidenze
originali; i log Inspect del gate sono conservati separatamente.

Reports e statistiche distinguono protocolli v1/v2; le coppie richiedono le
medesime condizioni registrate. Non è stato eseguito un benchmark a consumo.
Risultati dei test e problemi del dataset locale: `COST266_CONTINUOUS_VALIDATION.md`.
