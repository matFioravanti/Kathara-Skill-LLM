# Skill Gate con recupero automatico — validazione del 29 ottobre 2026

## Esito

**CERTIFIED per la consegna `enforced_read_v1` + `recovery_v1`, nel backend e nelle versioni testate.** Il runner ordinario esegue ora A protetta → verifica → eventuali retry → eventuale caricamento integrale → B nella stessa sessione → checker. Una mancata lettura autonoma non scarta la run. Errori di isolamento, hash, processo, autenticazione, continuità o consegna impediscono lo sblocco.

La run DNS reale su copia di `lab00_five_router`, prompt T1 e correction originali, ha terminato la pipeline con **132 controlli superati, 0 falliti**, `task_success=true`. La Skill è stata verificata al primo tentativo. Questa è una valutazione funzionale separata dal gate: la consegna dei byte non dimostra comprensione e non garantisce il successo di altre configurazioni.

La certificazione è riferita all'ambiente locale descritto e ai confini verificati: mount, identità, capability, configurazione degli strumenti, continuità e transizione. Non si estende al backend host, ad altre versioni/configurazioni o al vecchio protocollo strettamente bloccante senza `recovery_v1`, che conserva `unsupported_backend`.

## Conformità della lettura, consegna delle Skill e successo funzionale

Aggiornamento delle sole metriche, riferito al commit `7c0247ea6cc6c91b1b8280761784baf2ed6bd677` più le modifiche locali di questa verifica. I risultati dei piloti descritti nel resto del documento sono quelli precedenti: **non sono stati rieseguiti Codex, il checker o sandbox reali**.

Le tre dimensioni sono indipendenti:

1. **Lettura autonoma**: Codex ha letto tramite tool ogni Skill obbligatoria, con lettura dedicata e integrale verificata prima dell'apertura di B. `skill_autonomous_read_before_write` è `true` solo con queste prove, `false` quando almeno una Skill è stata consegnata tramite fallback verificato e `null` quando la prova è insufficiente o non applicabile. Anche un sollecito seguito da una lettura tramite tool conta come lettura autonoma, ed è identificato da `retry_verified`.
2. **Consegna**: `skill_delivery_before_write` indica se tutte le Skill obbligatorie sono state rese disponibili prima di B, tramite lettura verificata o fallback integrale verificato. Un valore `false` richiede una violazione dimostrata; un errore o un controllo incompleto da soli producono `null`. Il fallback prova la consegna dell'input al processo, non la comprensione del modello.
3. **Successo funzionale**: i risultati del Kathara Lab Checker misurano il laboratorio prodotto. Una lettura o una consegna verificata non implica la comprensione delle istruzioni né il successo funzionale.

`skill_delivery_details` espone per ogni Skill `method`, `autonomous_read_before_write` e `delivery_before_write`; supporta `read_verified`, `retry_verified` e `preloaded_fallback`, compresi metodi misti. Il fallback non aumenta il conteggio delle letture autonome.

### Problema precedente e correzione

L'osservatore precedente riceveva soltanto gli eventi protetti di A e dei retry. L'assenza delle modifiche di B in quello stream rendeva sconosciuto l'ordine lettura/modifica, con `required_reads_complete_before_modification=null` e `strict_status=unverified`, anche quando il gate aveva verificato il passaggio ad una B autorizzata.

Per `enforced_read_v1` con `recovery_v1`, il ricalcolo usa gli eventi salvati delle fasi protette, i loro risultati e hash attesi, la sequenza temporale `passed` → `write_phase_running`, l'isolamento, l'ID esplicito di sessione e il risultato del turno B. La prova di lettura proviene esclusivamente da A o dai retry: gli eventi B servono a verificare la transizione, mai a dimostrare una lettura precedente. I tentativi dichiarati devono corrispondere ai log presenti; sessioni, timestamp o log mancanti/contraddittori lasciano i valori sconosciuti. La stringa `CERTIFIED` da sola non produce `true`.

Per il fallback vengono verificati il messaggio salvato, la lunghezza e l'hash dell'input, gli hash dei singoli contenuti, l'esito della consegna e la stessa sessione. Un'incongruenza porta a `null`, non a una lettura inventata. Le prove di singole Skill possono restare note anche quando la conformità complessiva è sconosciuta.

Nel solo protocollo di recupero, i campi storici sono coerenti con le nuove dimensioni: `required_reads_complete_before_modification` rappresenta la lettura autonoma di tutte le Skill; `protocol_compliance_observed` rappresenta la consegna verificata secondo `recovery_v1`; `strict_status` è `verified` per letture tramite tool, `fallback_delivered` per consegna con fallback, `delivery_failed` per una violazione dimostrata e `unverified` quando mancano prove. I protocolli storici, incluso `explicit_read_v2`, mantengono la semantica precedente; `no_skill` e `auto` non ricevono valori positivi artificiali.

### Esempi dai log già esistenti

Il ricalcolo su una **copia temporanea** del pilota DNS reale precedentemente eseguito produce:

```json
{
  "skill_autonomous_read_before_write": true,
  "skill_delivery_before_write": true,
  "skill_delivery_details": {
    "kathara-dns": {
      "method": "read_verified",
      "autonomous_read_before_write": true,
      "delivery_before_write": true
    }
  }
}
```

Il caso retry esistente produce ugualmente `true/true`, con metodo `retry_verified`. Il caso fallback esistente produce `false/true`, con metodo `preloaded_fallback` e `strict_status=fallback_delivered`. Il pilota DNS precedente conserva il risultato funzionale registrato di 132/132; questa verifica non lo ha rieseguito e non ha modificato i suoi file originali.

### Aggregazione, test e limiti

`runs.csv` e il foglio Runs esportano le due metriche e i dettagli per Skill. Summary esporta separatamente conteggi e percentuali per lettura autonoma verificata, consegna verificata, fallback verificato, conformità sconosciuta ed errore tecnico, più una struttura JSON con conteggi, denominatori e percentuali per singola Skill. Le percentuali di lettura/consegna/fallback usano come denominatore le run con il relativo valore noto; sconosciuti ed errori tecnici usano tutte le run abilitate a `recovery_v1`. Gli errori tecnici comprendono `technical_error` del gate e gli stati di errore AUT, checker o correction della pipeline. Una run tecnica non viene contata anche tra gli sconosciuti; le altre dimensioni possono sovrapporsi, per esempio consegna e fallback. Se il denominatore è zero, la percentuale è `null`.

Verifiche deterministiche finali:

- Test mirati richiesti: **103 superati, 0 falliti, 0 saltati**.
- Suite completa con guardia temporanea: **272 superati, 0 falliti, 4 saltati**, più 12 sottotest superati. Tre skip sono i test Docker opt-in; il quarto è il test preesistente che crea un sandbox shell reale, saltato per rispettare la richiesta. La guardia impedisce anche l'avvio reale di Codex, Docker, Kathara e checker durante i test. Tre warning preesistenti `pkg_resources`.
- I test coprono lettura iniziale/retry, fallback, entrambe le Skill e metodi misti, gate incompleto, errore tecnico, letture solo in B, hash errato, output troncato, sessione diversa, log retry mancanti, timestamp incoerenti e denominatori.
- CSV ed Excel sono stati rigenerati solo in `/private/tmp/tesi-skill-conformita-l34_4f2y/results`: 3 run copiate, 132 righe di check già esistenti e intestazioni CSV/fogli Excel corrispondenti. I valori `true`, `false` e celle vuote sono verificati anche con fixture sintetiche. Il file temporaneo `validation.json` descrive il ricalcolo.
- Confrontati con gli oggetti Git **5.476 file tracciati** in `runs`, `scenarios`, `skills`, `results` e `prompt`: **0 modificati, 0 mancanti**; presenti 76 manifest storici. `benchmark.yaml`, protocollo del sandbox e meccanismo di recupero non sono stati modificati.

Comandi eseguiti:

```bash
.venv/bin/python -m pytest -v tests/test_skill_gate_recovery.py \
  tests/test_skill_gate.py tests/test_aut_observation.py
PYTHONPATH=/private/tmp PYTEST_ADDOPTS='-p tesi_skill_metrics_pytest_guard' \
  .venv/bin/python -m pytest -q
git diff --check
```

Limite: i nuovi valori vengono calcolati quando si producono o ricalcolano le metriche; i JSON/CSV/Excel ufficiali già salvati non sono stati riscritti. Per derivare un valore positivo servono gli artefatti di fase, risultato, invocazione, sessione e cronologia coerenti: se sono assenti, la metrica rimane `null`. Questo controllo non dimostra la comprensione del modello e non modifica l'architettura A → Gate → B.

## Stato iniziale e versione

`HEAD` iniziale e commit di riferimento: `115a21feb7e889383c3d5b78594f895b88aff865`. Nessun commit successivo, working tree inizialmente pulito. Esaminati i file richiesti, la cronologia e gli esperimenti precedenti. Il codice testato è quel commit più le modifiche locali elencate in `skill_gate_recovery_code_versions.json`, con SHA-256 dei file. Nessun commit o push automatico.

Il rapporto precedente è conservato in `skill_gate_validation_before_recovery.md`; i precedenti log e rapporti di validazione non sono stati riscritti.

Ambiente effettivo:

- macOS; Python e virtualenv 3.14.6, pytest 9.1.1.
- Codex host 0.157.1; Codex sbx 0.149.1; help reale di `exec resume` verificato.
- Docker Engine 29.8.0; sbx client/daemon 0.48.0, operativi.
- Template `docker/sandbox-templates:codex-docker`; immagine `kathara/base` già disponibile.
- Kathara 3.8.3; Kathara Lab Checker 0.1.14.
- Modello già configurato `gpt-5.6-terra`, reasoning `low`.
- Login/proxy esistenti; nessuna nuova chiave, nessuna credenziale esportata nei log.

## Implementazione nel runner ordinario

`inspect_runner.run_aut()` prepara la copia isolata e le Skill delle sole modalità previste, poi seleziona `run_recovery_gate()` quando sono configurati `enforced_read_v1` e `recovery_v1` e ci sono Skill obbligatorie. Il backend host resta escluso.

L'orchestrazione è in `benchmark_core/skill_gate.py`; il ciclo di vita utilizza `ProtectedCodexSession` in `docker_sandbox_runner.py`, riutilizzando gli helper sbx esistenti per eseguibile, network policy e cleanup con retry limitato. Il pilota usa questo stesso runner, non una seconda implementazione del gate.

### A protetta e lettura iniziale

Il laboratorio è esportato `:ro`; l'unico altro export host è la directory temporanea dello stato Codex. Il primo prompt richiede soltanto la lettura completa, una operazione dedicata per Skill, senza configurare il laboratorio. Nessun prompt funzionale viene inviato in A.

Prima della chiamata vengono confrontati i byte canonici, la copia staged e gli hash registrati nel manifest. Il verificatore controlla file corretto, contenuto integrale, hash, comando completato con exit 0, lettura dedicata e turno riuscito. Una dichiarazione dell'assistente non costituisce evidenza.

### Retry nella stessa sessione

Per impostazione predefinita sono consentiti **2 tentativi aggiuntivi**, configurabili con `aut.skill_gate_max_retries` tra 0 e 10. I limiti non interi, booleani o fuori intervallo sono rifiutati. Non esistono cicli illimitati.

Ogni sollecito elenca soltanto le Skill ancora mancanti. Le letture verificate vengono conservate individualmente e non richieste nuovamente. Ogni turno usa `codex exec resume ID`, controlla `thread.started` e richiede lo stesso ID; non usa `--last` o `--ephemeral`. Tentativi e sessioni sono contatori distinti. Non viene allocata una nuova `rNNN`.

Un comando di lettura fallito/incompleto resta una mancata lettura e attiva il recupero. Timeout del processo Codex, errore del turno, ID mancante/diverso o alterazione del baseline sono errori tecnici e non attivano un nuovo thread indipendente.

### Fallback deterministico

Esauriti i tentativi, Python rilegge **solo le Skill mancanti** dai file canonici, ricontrolla i byte e gli SHA-256 registrati, quindi costruisce un messaggio separato dal prompt funzionale. Ogni `SKILL.md` è incluso integralmente tra delimitatori, senza riscritture, riassunti o normalizzazione dei newline.

Il payload UTF-8 viene salvato prima dell'avvio e consegnato come byte allo stdin del processo. Vengono registrati lunghezza, SHA-256 e comando; sono richiesti completamento positivo e ID invariato. Il file salvato deve coincidere esattamente con il payload e contenere tutti i byte delle Skill previste. Troncamenti locali o cambiamenti degli hash bloccano il gate. I test includono newline CRLF.

Il fallback rimane nella fase protetta. Il gate registra per ciascuna Skill:

- `read_verified`: lettura tramite tool al primo turno;
- `retry_verified`: lettura tramite tool dopo sollecito;
- `preloaded_fallback`: contenuto integrale caricato dall'orchestratore.

Il terzo metodo prova la disponibilità nell'input consegnato al processo, non una lettura autonoma, né comprensione o applicazione. Le metriche di osservazione delle letture escludono il contenuto del fallback.

### Sblocco e B

Il baseline, comprese le Skill staged, viene ricontrollato dopo i turni e prima dello sblocco; i file canonici non devono essere cambiati. Il sandbox A viene eliminato prima di creare il sandbox B scrivibile. Lo stato persistente della CLI conserva la stessa sessione.

B riceve **il prompt funzionale originale**, senza reinserire tutte le Skill. Il runner conserva anche le modifiche parziali quando B fallisce. La sincronizzazione usa `copy_lab()` senza dereferenziare link esterni. La pipeline ordinaria prosegue normalmente verso il checker dopo un AUT riuscito; gli errori tecnici conservano il comportamento di errore preesistente.

L'orchestratore non genera configurazioni DNS/routing e non corregge l'output dell'agente.

## Isolamento verificato

Ogni processo è avviato con UID/GID non privilegiati corrispondenti al proprietario della copia temporanea, senza gruppi supplementari, `NoNewPrivs=1` e capability effettive, permesse, ereditabili, ambient e bounding tutte nulle. Nell'ambiente testato UID 501/GID 20. Il launcher root serve esclusivamente ad applicare irrevocabilmente queste restrizioni prima dell'esecuzione di Codex.

Un wrapper fidato emette l'attestazione dell'identità immediatamente prima di `exec` nello stesso processo; UID e capability vengono controllati anche nei turni reali. Non è una dichiarazione generata dal modello. La policy interna Codex rimane attiva (`read-only` in A, `workspace-write` in B, approvazioni `never`); non si usa il bypass della sandbox per far passare il flusso.

La configurazione del template viene ridotta al solo provider proxy necessario all'autenticazione. Non vengono ereditati MCP, hook, plugin o istruzioni del template. Il login è verificato con l'identità ristretta; i collegamenti alla configurazione/auth del proxy restano interni al sandbox. `codex mcp list --json` deve risultare privo di server abilitati.

Il probe indipendente, eseguito con lo stesso launcher:

- legge `lab.conf`, verifica negazione di scrittura con `EROFS` in A e scrittura possibile in B;
- verifica directory dello stato scrivibile e baseline invariato;
- controlla UID, tutti i set di capability e no-new-privileges;
- nega `sudo -n true`, accesso a tre socket Docker/containerd e porte Docker locali 2375/2376;
- controlla dalla mount table che gli unici export host siano laboratorio corrente e stato;
- verifica configurazione MCP, autenticazione e policy di rete prevista dal progetto.

Il confronto reale preesistente rw/ro usa due sandbox indipendenti, identici permessi Unix scrivibili e lo stesso utente. Scritture shell/Python, creazione, eliminazione, modifica startup e accesso tramite symlink riescono sul mount scrivibile e sono negate sul mount ro; chmod, chown e rimontaggio non aggirano la protezione. Gli hash confermano laboratorio ro invariato e rw cambiato. La sintassi sbx scrivibile è il mount predefinito senza suffisso, non `:rw`.

Questi sono controlli concreti del confine configurato, non una prova contro vulnerabilità del kernel o ogni servizio/configurazione immaginabile. Nel nuovo pilota il prompt A richiede soltanto lettura: non si attribuisce al modello un tentativo di scrittura che non appare nei suoi eventi. La negazione nel nuovo launcher è misurata dal probe indipendente; il precedente pilota conserva inoltre un tentativo reale Codex negato. Non vengono confusi test simulati e isolamento reale.

## Evidenze separate e compatibilità

Ogni run conserva:

```text
logs/aut/skill_gate.json
logs/aut/phase_a/{events.jsonl,prompt_sent.md,result.json,stderr.log,invocation.json}
logs/aut/retries/attempt_01/...
logs/aut/retries/attempt_02/...
logs/aut/fallback/...
logs/aut/phase_b/...
logs/aut/isolation_protected.json
logs/aut/isolation_writable.json
```

L'evidenza di un tentativo deve coincidere con il relativo artefatto salvato. Il verificatore accetta solo A o un percorso retry autorizzato, mai B/fallback o il vecchio stream aggregato come sostituto. Le letture B non possono sbloccare retroattivamente A.

Per Inspect e i consumatori storici sono prodotti anche `events.jsonl`, `result.json`, `invocation.json`, `stderr.log` e `prompt_sent.md` al livello superiore. Nel solo stream aggregato gli ID dei tool sono prefissati dalla fase: Codex riavvia la numerazione a ogni turno e altrimenti le osservazioni precedenti verrebbero sovrascritte. I log grezzi per turno rimangono invariati. Gli aggregati del primo esperimento esplorativo sono stati rigenerati dai log grezzi dopo questa correzione, senza richiamare il modello.

`no_skill` e `auto` mantengono il runner ordinario senza gate obbligatorio. Le modalità obbligatorie mantengono esattamente le Skill richieste: Creation, DNS oppure entrambe. `explicit_read_v2` conserva il proprio percorso. La versione di recupero è una dimensione di raggruppamento distinta: non viene aggregata con il vecchio protocollo bloccante.

## Test eseguiti

Tutti i test deterministici e i tre test reali di isolamento sono passati **prima** dei piloti con modello. Eseguite ulteriori regressioni dopo le correzioni.

| Categoria | Superati | Falliti | Saltati | Evidenza |
|---|---:|---:|---:|---|
| Suite finale | 250 | 0 | 3 | `skill_gate_recovery_suite.xml`; altri 12 sottotest passati |
| Gate, recupero, osservazioni mirati | 80 | 0 | 0 | `skill_gate_recovery_targeted.xml` |
| Nuovi test recupero/launcher/pipeline | 29 | 0 | 0 | Inclusi negli 80 e nei 250 |
| Isolamento Docker reale | 3 | 0 | 0 | `skill_gate_recovery_isolation.xml` |
| Casi Codex reali | 5 | 0 | 0 | Quattro casi richiesti più esplorazione iniziale conservata |
| Checker DNS reale | 132 | 0 | 0 | Controlli funzionali, non test pytest |

Le categorie si sovrappongono e non vanno sommate. I tre skip della suite sono i test opt-in: probe ro, launcher di produzione A/B e comparazione rw/ro. Eseguiti separatamente con `RUN_SBX_ISOLATION_TESTS=1`, tutti passati. Tre warning preesistenti di deprecazione `pkg_resources`.

I test unitari usano sessioni/processi deterministici e checker simulati per verificare la macchina a stati. Non costituiscono prove del kernel/mount. Verificano letture complete, mancanti, parziali, errate, troncate, exit errato, hash errato, due Skill e caricamento misto; retry limitati, richieste delle sole Skill mancanti, fallback integro/troncato, continuità mancante/diversa, timeout, identità privilegiata, baseline/canonico alterato e mancato avvio di B sugli errori. Tre integrazioni deterministiche verificano il runner ordinario fino al checker simulato nelle modalità obbligatorie. Le altre modalità e i protocolli precedenti sono coperti dalla regressione esistente.

Problemi individuati e corretti:

1. Una fixture normalizzava CRLF con `read_text()`, facendo fallire correttamente l'hash: la simulazione ora restituisce i byte effettivi come un `cat`.
2. Nel primo caso reale Codex aveva concatenato `wc` e lettura. Il gate ha rifiutato la lettura non dedicata e il retry è riuscito. Il prompt è stato reso esplicito su `cat` separato e divieto di concatenazione; una sola nuova verifica ha dimostrato lettura immediata.
3. ID dei tool riutilizzati tra turni: risolto il rischio di perdita delle osservazioni nel log compatibile.
4. I tempi dei turni falliti vengono ricavati anche dai risultati parziali; nessuna misura mancante diventa automaticamente zero.
5. L'export iniziale dei piloti restituiva zero righe perché le copie `case/run` non hanno il layout `scenario/T/mode/rNNN`: aggiunto adattatore temporaneo che verifica esplicitamente il numero delle righe esportate.
6. Il postprocessore distingueva male i file di prompt controllato dalle directory retry: ora seleziona solo directory.

Un comando mirato indicava inizialmente un file test inesistente e non ha eseguito test; è stato corretto usando i file effettivi. Non viene contato come test superato. Tutti gli errori risolvibili sopra sono stati corretti e verificati; nessun fallimento finale.

## Piloti reali

Evidenze complete in `skill_gate_recovery_pilot/`; la verifica diretta dopo la correzione del prompt è in `skill_gate_recovery_direct_after_fix/`. Tutte le invocazioni usano Codex reale e il login/proxy esistente. **15 turni complessivi**, senza retry automatici dei casi già eseguiti; il pilota rifiuta directory di caso esistenti e impone un budget di chiamate per invocazione.

| Caso | Intervento controllato | Metodo registrato | Turni | Esito |
|---|---|---|---:|---|
| Prima esplorazione della lettura immediata | Nessuno; lettura concatenata rifiutata | `retry_verified` | 3 | B completata, run conservata |
| Lettura immediata dopo correzione | Nessuno | `read_verified` | 2 | B completata |
| Omissione iniziale | Primo prompt sostituito esplicitamente con istruzione di non leggere | `retry_verified` | 3 | Sollecito e B nella stessa run |
| Fallback | I tre turni di lettura ricevono l'istruzione controllata di non leggere | `preloaded_fallback` | 5 | Byte caricati, hash/consegna verificati, B completata |
| DNS reale | Nessuno; Skill, prompt T1 e correction originali | `read_verified` | 2 | Pipeline e checker completati, 132/132 |

Nei casi controllati sono salvati sia il prompt richiesto dal gate sia quello effettivamente inviato. L'omissione è un intervento sperimentale dichiarato; non sono simulati output del modello, verifiche, caricamento fallback, ripresa o checker. Il fallback non viene conteggiato come lettura autonoma. Tutti gli ID iniziali, di retry/fallback e di B coincidono entro ciascun caso; 1 sessione per caso.

Per la run DNS: ID `01a18712-354b-78f2-a42c-58bd9bf64541`; A 8,0551 s; processi Codex complessivi 161,0107 s; overhead sandbox 49,0160 s; gate completo 210,6047 s; checker 22,0135 s; pipeline totale 232,7688 s. Token input 165.737, output 5.194, totale calcolato 170.931; cached input 137.984 già compreso nell'input. Nessuna somma aggiuntiva dei cached/reasoning token.

## Metriche e aggregati

Le metriche richieste vengono salvate in `skill_gate.json`, copiate nel manifest dalla pipeline, esportate in `evaluation/metrics.json`, CSV Runs/Summary ed Excel. Comprendono metodi per Skill, tentativi/retry, fallback e relativi hash/consegna, sessione/continuità, isolamento, stato/certificazione, tutti i tempi e i token delle fasi. I valori non osservati restano `null`. Il risultato compatibile contiene la somma dei turni distinti, non l'ultimo usage di B.

Summary distingue politica di recupero e metodi di consegna, con conteggi e percentuali delle run con gate di recupero abilitato. Una run mista può apparire in più categorie di metodo; le categorie non sono necessariamente esclusive. Per il vecchio protocollo, privo di classificazione del metodo, il denominatore di consegna è zero e le percentuali sono nulle. Le medie delle fasi sono esportate separatamente.

`skill_gate_recovery_results/` contiene **5 run, 132 check e 5 gruppi**, senza ID duplicati. Header CSV uguali ai fogli Runs/Checks/Summary del workbook. Le misure dei tre piccoli casi AUT sono derivate dai log reali; non essendo stati eseguiti con il checker, durata totale di pipeline e misure checker restano nulle.

L'aggregazione storica è stata rigenerata solo in `/private/tmp/tesi-skill-gate-recovery-historical-results`: **76 run, 32.257 check, 76 gruppi**, con header CSV/Excel coerenti. Evidenza: `skill_gate_recovery_export_validation.json`.

Confrontati **5.476 file tracciati** sotto runs, scenarios, skills, results e prompt con gli oggetti Git: **0 modifiche**, 76 manifest storici. Evidenza: `skill_gate_recovery_integrity.json`. Checker e correction non sono stati modificati. Dopo i piloti `sbx ls --json` restituisce `[]`; nessun container Kathara residuo.

## File modificati e limiti

Modificati `benchmark.yaml`, `skill_gate.py`, `docker_sandbox_runner.py`, `inspect_runner.py`, `config.py`, `run_metrics.py`, `aggregation.py`, lo script pilota e il test sbx; aggiunto `tests/test_skill_gate_recovery.py`. `pipeline.py`, `skill_modes.py`, `workspace.py`, runner host e codice del checker sono riutilizzati senza modifica in questa implementazione.

Limiti: il backend supportato è esclusivamente Docker Sandbox nelle versioni provate; la ripresa richiede stato persistente leggibile e stesso thread ID. Un payload non accettato per limiti tecnici del modello/CLI termina con errore infrastrutturale, senza fingere una nuova sessione equivalente. Non si misura la comprensione e non si garantisce che un modello applichi correttamente le istruzioni. Le modalità Creation e Both sono integrate e verificate deterministicamente fino al checker simulato; il solo pilota funzionale con checker reale è DNS, come richiesto. Non è stato rieseguito il benchmark completo.

## Comandi

Configurazione ordinaria già impostata in `benchmark.yaml`:

```yaml
aut:
  skill_protocol: enforced_read_v1
  skill_gate_recovery_policy: recovery_v1
  skill_gate_max_retries: 2
```

Avvio ordinario, che crea una nuova run senza riscrivere quelle storiche:

```bash
.venv/bin/python scripts/run_benchmark.py --scenario lab00_five_router \
  --prompt-type T1 --skill-mode dns_only --repetitions 1
```

Verifiche eseguite:

```bash
.venv/bin/python -m pytest -q --junitxml=reports/skill_gate_recovery_suite.xml
.venv/bin/python -m pytest -v tests/test_skill_gate_recovery.py \
  tests/test_skill_gate.py tests/test_aut_observation.py \
  --junitxml=reports/skill_gate_recovery_targeted.xml
RUN_SBX_ISOLATION_TESTS=1 .venv/bin/python -m pytest -v \
  tests/test_skill_gate_sbx_integration.py tests/test_skill_gate_mount_comparison.py \
  --junitxml=reports/skill_gate_recovery_isolation.xml
.venv/bin/python scripts/skill_gate_pilot.py --recovery --case immediate
.venv/bin/python scripts/skill_gate_pilot.py --recovery --case retry
.venv/bin/python scripts/skill_gate_pilot.py --recovery --case fallback
.venv/bin/python scripts/skill_gate_pilot.py --recovery --case dns_real
.venv/bin/python scripts/skill_gate_pilot.py --recovery --case immediate \
  --output reports/skill_gate_recovery_direct_after_fix
.venv/bin/python scripts/skill_gate_pilot.py --recovery --export-only \
  --include reports/skill_gate_recovery_direct_after_fix
.venv/bin/python scripts/aggregate_results.py --runs runs \
  --output /private/tmp/tesi-skill-gate-recovery-historical-results
```

I comandi con modello non vanno ripetuti automaticamente: i risultati sono già conservati e lo script rifiuta casi esistenti. L'export-only non chiama il modello. Per tornare a `explicit_read_v2`, impostare quel protocollo e rimuovere la politica di recupero; per mantenere la vecchia semantica strettamente bloccante, usare `enforced_read_v1` senza `skill_gate_recovery_policy`.
