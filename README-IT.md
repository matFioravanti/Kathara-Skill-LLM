# Kathara Skill LLM Benchmark

Benchmark riproducibile per valutare agenti LLM CLI che configurano DNS e servizi web in laboratori di emulazione di rete Kathara. Gli agenti supportati sono **Codex CLI** e **Antigravity CLI (agy)**, ciascuno con autenticazione rigorosamente locale. Per Codex è inoltre supportata l'esecuzione totalmente isolata all'interno di container effimeri gestiti tramite **Docker Sandboxes (`sbx`)**.

## Architettura

Ogni scenario contiene un prompt di compito, un laboratorio iniziale immutabile (baseline) e una correction manuale canonica. Per ciascuna modalità Skill, il benchmark runner alloca una directory di run indipendente in `runs/<scenario>/<prompt_type>/<skill_mode>/rNNN`, conserva il baseline originale in `input/lab`, alloca la copia modificabile in `lab` e avvia l'Agent Under Test (AUT). I progressivi numerici delle run avanzano indipendentemente per scenario e modalità.

L'**active agent** di una run è unico: l'agente configurato agisce come AUT. Non è consentito combinare agenti differenti all'interno della medesima run.

Terminata l'esecuzione dell'AUT (con successo, per timeout o per errore), il runner chiude la finestra temporale di misurazione, salva gli eventi di telemetria, sincronizza i file risultanti e calcola il diff rispetto al laboratorio originale. Il Kathara Lab Checker valuta quindi il `lab/` della run usando la correction manuale canonica `scenarios/<scenario>/correction.yaml`. Uno snapshot byte per byte viene salvato in `evaluation/correction.yaml` per garantire la riproducibilità totale della valutazione. La correction rimane rigorosamente fuori da `lab/` e non entra mai a contatto con l'AUT.

Il verdetto finale del task deriva esclusivamente dal checker:
- Una run conclusa con successo può avere `aut_execution_success=true`, `checker_execution_success=true` e `task_success=false`.
- In caso di anomalie infrastrutturali o errori tecnici durante l'esecuzione dell'AUT o del checker, `task_success` rimane `null` e la run assume uno stato di errore pipeline (`AUT_FAILED`, `CHECKER_FAILED`, ecc.).

```text
Prompt + Skill
      │
      ▼
Backend di Esecuzione AUT
  ├─ Host CLI: Codex / Antigravity CLI
  └─ Docker Sandbox (sbx): Container Effimero
      │
      ├── result.json
      ├── events.jsonl
      └── sandbox_metadata.json (sbx)
              │
              ▼
        Inspect Adapter
              │
              └── run_id.eval (Log nativo Inspect AI garantito)

Laboratorio Generato (lab/)
      │
      ▼
scenarios/<scenario>/correction.yaml
      │
      ▼
evaluation/correction.yaml ──► Kathara Lab Checker
                                      │
                                      └── Risultati Checker (CSV)

run_id.eval ────────┐
                    ├── aggregazione ──► runs.csv / checks.csv / summary.csv / benchmark.xlsx
risultati checker ──┘
```

### Backend di Esecuzione Codex

Codex supporta due backend di esecuzione, selezionabili in `benchmark.yaml`:

1. **Backend Host CLI** (`execution_backend: codex_cli` o assente):
   Esegue `codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` direttamente sulla macchina host in una directory temporanea isolata, inviando il prompt via stdin e registrando tutti gli eventi JSONL.
2. **Backend Docker Sandbox (`sbx`)** (`execution_backend: docker_sandbox`):
   Esegue Codex all'interno di un sandbox monouso isolato gestito da Docker Sandboxes (`sbx` v0.48.0).
   - **Ciclo di vita effimero**: Ogni run alloca un sandbox dedicato con nome univoco (`kathara-<scenario>-r<repetition>-<uuid8>`) tramite `sbx create` con `--skills=off`. Al termine (successo, errore, timeout o interruzione), il sandbox viene distrutto con `sbx rm --force` (con retry). Se la rimozione fallisce, la run viene marcata con `SandboxCleanupError`.
   - **Bind-mount diretto del laboratorio**: I file temporanei del laboratorio sono montati direttamente nel container: ogni modifica di Codex viene scritta istantaneamente sul disco host senza ricorrere a `sbx cp`.
   - **Nessuna esposizione delle credenziali host**: L'autenticazione usa esclusivamente il proxy OAuth ufficiale di Docker Sandboxes. Nessun file di credenziali dell'host viene montato nel sandbox.
   - **Network policy restrittiva in uscita**: L'accesso di rete è rigorosamente limitato agli endpoint autorizzati OAuth e API OpenAI; qualsiasi traffico non autorizzato viene bloccato.
   - **Memoria interna disabilitata esplicitamente**: La memoria persistente di Codex viene disattivata con opzioni e flag multipli (`--disable memories`, `-c memories=false`, `-c memories.use_memories=false`, `-c memories.generate_memories=false`, `-c features.memories=false`) per prevenire contaminazioni tra run.
   - **Isolamento del checker sull'host**: Kathara e Kathara Lab Checker operano esclusivamente sull'host e non vengono mai montati o eseguiti nel sandbox.
   - **Nessun fallback silenzioso**: Errori tecnici del sandbox bloccano la run e non provocano mai un fallback trasparente all'host.

### Backend Antigravity

`agy --add-dir <workspace> --dangerously-skip-permissions --output-format stream-json --model <model> --effort <effort> --print <prompt>` esegue Antigravity CLI con login Google locale all'interno di un workspace isolato.

### Telemetria Inspect AI e Resilienza agli Errori

Al termine della sessione AUT, un adapter dedicato legge `result.json`, `events.jsonl` e gli eventuali metadati del sandbox per generare un log di telemetria nativo Inspect AI:
```text
runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/logs/aut/<scenario>__<prompt_type>__<skill_mode>__rNNN.eval
```
Il file traccia token in ingresso/uscita, token di reasoning, token in cache, durata, chiamate a tool, diagnostica degli errori e metadati. È ispezionabile con `inspect log dump` o `read_eval_log`.

Inspect AI funge da puro osservatore di telemetria: non avvolge il subprocess AUT, non altera `correction.yaml` e non interviene nella valutazione del laboratorio.

**Resilienza e Diagnostica:**
- **Creazione del log garantita**: Il log `.eval` viene prodotto anche in caso di timeout, crash del processo AUT o errori nella sincronizzazione del workspace, evitando perdite di traccia.
- **Preservazione dei diff parziali**: La sincronizzazione del laboratorio adotta uno staging temporaneo (`lab.sync-tmp` -> `lab`). Se l'AUT si interrompe dopo aver modificato alcuni file, le modifiche parziali vengono salvate e registrate in `logs/diff.json`.
- **Tracciamento diagnostico**: In caso di fallimento infrastrutturale, stack trace e messaggi di errore sono registrati in `logs/pipeline_error.log`, `manifest.json` e `evaluation/metrics.json` nei campi `pipeline_error` e `sandbox`.

## Requisiti e installazione

- **Python**: 3.11 o successivo
- **Docker**: Daemon Docker attivo (Docker Desktop su macOS)
- **Kathara**: Installato e funzionante per l'emulazione di rete
- **Prerequisiti agente** (è richiesto solo l'agente configurato):
  - **Codex (Host)**: Codex CLI installata e autenticata con ChatGPT (`codex --version`, `codex login status`).
  - **Codex (Docker Sandbox)**: Docker Sandboxes CLI installata (`sbx version` v0.48.0), daemon sbx attivo o con avvio automatico, e Codex autenticato nel template sandbox.
  - **Antigravity**: Antigravity CLI installata con login Google locale (`agy --version`).

Configurazione dell'ambiente virtuale:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` è il freeze delle dipendenze verificate:
Inspect AI 0.3.266, Inspect SWE 0.2.71, kathara-lab-checker 0.1.14, Kathara 3.8.3, pandas 3.0.6, PyYAML 6.0.3 e openai 3.16.2.

Non impostare `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY` o `INSPECT_EVAL_MODEL`: il runner le rimuove dall'ambiente subprocess per garantire l'uso dell'autenticazione locale.

## Configurazione

Ogni agente dispone del proprio file di configurazione:

* `benchmark.yaml` — configurazione **Codex** (`gpt-5.6-terra`, reasoning effort `low`)
* `benchmark_antigravity.yaml` — configurazione **Antigravity** (`gemini-3.8-flash`, reasoning effort `low`)

L'agente attivo è specificato in `aut.agent`. L'opzione CLI `--agent` funge da verifica di coerenza: deve coincidere con `aut.agent` nel file YAML, altrimenti il comando viene rifiutato.

### Configurazione Docker Sandbox (`benchmark.yaml`)

Per Codex, il blocco `docker_sandbox` controlla il backend sbx:

```yaml
docker_sandbox:
  execution_backend: docker_sandbox  # "docker_sandbox" per abilitare sbx; assente/altro = host CLI
  sbx_version: "0.48.0"              # versione sbx attesa (EXPECTED_SBX_VERSION)
  codex_version: "0.149.1"           # versione codex nel template sandbox sbx
  auto_start_daemon: true            # avvia automaticamente il daemon sbx se spento
  auto_start_docker: true            # avvia Docker Desktop su macOS se spento
  daemon_wait_seconds: 30            # timeout di attesa avvio daemon
  docker_wait_seconds: 45            # timeout di attesa avvio Docker Desktop
  cleanup_on_error: true             # elimina il container anche in caso di errore
  verify_sandbox_codex: true         # verifica versione e login di Codex dentro il sandbox in preflight
```

### Correction degli scenari

Ogni scenario adotta una correction canonica condivisa in `scenarios/<scenario>/correction.yaml`. Il preflight ne convalida presenza e correttezza sintattica prima di avviare qualsiasi chiamata modello. La correction non entra mai in `lab/` né viene fornita all'AUT.

## Skill richieste

Il repository organizza le skill in `skills/`:

```text
skills/kathara-creation/SKILL.md
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
scenarios/<scenario>/correction.yaml
```

La Creation Skill deve dichiarare `name: kathara-creation` e la DNS Skill `name: kathara-dns`; entrambe richiedono il campo `description`. Per convalidare le skill:

```bash
python scripts/run_benchmark.py --check-skills
```

### Modalità Skill (Codex)

Le run Codex selezionano una delle cinque modalità con `--skill-mode`:

| Modalità | Skill rese disponibili | Direttiva nel prompt |
|---|---|---|
| `no_skill` | Nessuna | Nessuna |
| `creation_only` | Creation (`kathara-creation`) | `$kathara-creation` |
| `dns_only` | DNS (`kathara-dns`) | `$kathara-dns` |
| `both_forced` | Creation + DNS | Entrambe |
| `auto` | Creation + DNS | Nessuna (scoperta autonoma) |

### Protocollo Skill

Il benchmark adotta il protocollo `explicit_read_v1` per Codex:
- Nelle modalità forzate (`creation_only`, `dns_only`, `both_forced`), il runner aggiunge un'istruzione esplicita e standardizzata di lettura del file `SKILL.md` corrispondente oltre alla direttiva `$skill`.
- Nella modalità `auto`, le skill vengono inserite in `lab/.codex/skills/` senza modifiche al prompt, lasciando agire la discovery nativa.
- Nella modalità `no_skill`, non viene fornita alcuna skill.

Il benchmark registra il trattamento effettivo:
- `skill_mode`
- `available_skills`
- `forced_skills`
- `skill_protocol`

Il runner non deduce l'aderenza alla skill dall'esecuzione dei comandi shell, poiché il caricamento nativo delle skill può non risultare osservabile nei comandi eseguiti. L'esito finale viene verificato in modo deterministico dal Kathara Lab Checker.

Eseguire in sequenza tutte le cinque modalità:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --all-skill-modes
```

Rivalutare le run esistenti in-place con la correction canonica aggiornata, senza chiamate LLM:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --rerun-correction
```

## Scenari

Gli scenari vengono scoperti automaticamente nella directory `scenarios/`:

```text
scenarios/<scenario_id>/
├── correction.yaml
├── metadata.yaml        # Metadati descrittivi facoltativi (topologia, difficoltà)
└── lab/
    └── lab.conf
```

I prompt risiedono esclusivamente in `prompt/<scenario_id>/<prompt_type>.md` (T1–T6).

```bash
# Eseguire un singolo scenario con prompt T1
python scripts/run_benchmark.py --scenario static-routing-5routers --prompt-type T1 --skill-mode dns_only

# Eseguire tutte le modalità skill per uno scenario
python scripts/run_benchmark.py --scenario static-routing-5routers --prompt-type T1 --all-skill-modes

# Eseguire 5 ripetizioni di tutti gli scenari su tutte le modalità skill
python scripts/run_benchmark.py --all --prompt-type T1 --all-skill-modes --repetitions 5
```

## Esecuzione

Attiva l'ambiente virtuale prima di ogni comando:

```bash
source .venv/bin/activate
```

### Preflight

Il preflight controlla skill, autenticazione dell'agente, Docker, Kathara e checker senza spendere token:

```bash
# Preflight Codex (valida Host CLI o Docker Sandbox sbx in base a benchmark.yaml)
python scripts/run_benchmark.py --preflight --agent codex

# Preflight Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --preflight --agent antigravity
```

### Esecuzione delle run

```bash
# Esecuzione con Codex
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --agent codex

# Esecuzione con Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --scenario example_dns_001 --prompt-type T1 --agent antigravity
```

L'impostazione `benchmark.continue_on_error` determina se proseguire dopo una run fallita a livello infrastrutturale. Un laboratorio valutato e bocciato dal checker è una run regolarmente conclusa, non un errore.

## Artefatti e stati

Ciascuna run archivia la documentazione completa in `runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/`:

```text
runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/
├── manifest.json
├── input/
│   ├── lab/                  # Snapshot originale immutabile
│   └── prompt.md
├── lab/                      # Laboratorio modificato dopo l'AUT
├── evaluation/
│   ├── correction.yaml       # Snapshot dell'input di valutazione canonico
│   └── metrics.json          # Metriche normalizzate della run
├── results/                  # Report CSV del Kathara Lab Checker
└── logs/
    ├── aut/                  # events.jsonl, result.json, invocation.json, prompt_sent.md,
    │                         # sandbox_metadata.json (sbx), <run_id>.eval
    ├── diff.json             # Diff rispetto al baseline iniziale
    ├── pipeline_error.log    # Log di errore dettagliato (in caso di fallimento)
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

### Metadati e metriche

- **`manifest.json`**: Registra timestamp, versioni (`codex_host_version`, `codex_sandbox_version`, `sbx_version`), backend di esecuzione (`codex_cli` o `docker_sandbox`), metadati del sandbox (`sandbox_name`, `sandbox_id`, `sandbox_cleanup_ok`), digest SHA-256 e cronologia degli stati pipeline.
- **`evaluation/metrics.json`**: Record normalizzato contenente stato (`COMPLETED`, `AUT_FAILED`, `CHECKER_FAILED`), successo AUT, punteggi del checker, token e durate.
- **Metriche temporali**:
  - `agent_seconds`: Durata del processo LLM.
  - `sandbox_overhead_seconds`: Tempo impiegato per creazione e rimozione del sandbox Docker.
  - `checker_seconds`: Tempo di esecuzione di `kathara-lab-checker`.
  - `total_seconds`: Durata totale della run dall'allocazione del workspace alla finalizzazione.
- **Coerenza metrica dei token**:
  - Estratti dall'ultimo evento `turn.completed` con blocco `usage`.
  - `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`.
  - `output_tokens`, `reasoning_output_tokens` (i reasoning token sono un sottoinsieme dei token di output e non vengono sommati due volte).
  - `total_reported`: Totale comunicato direttamente dalle API del modello.
  - `total_calculated`: Somma calcolata `input_tokens + output_tokens`.
  - `total`: Valore effettivo che privilegia `total_reported` se presente, altrimenti `total_calculated`.
- **Telemetria di campionamento LLM**: salvata in `logs/aut/sampling_telemetry.json`, `evaluation/metrics.json`, metadati Inspect e report aggregati; non modifica punteggi, token o tempi.

### Configurazione ed evidenza della telemetria di campionamento

```yaml
aut:
  sampling_telemetry:
    enabled: true
    mode: passive  # passive | http_trace
```

Se la sezione è assente o `enabled: false`, la raccolta è disabilitata. La run registra `disabled` senza leggere i log di sampling né aggiungere impostazioni diagnostiche. Le configurazioni precedenti restano valide.

`passive` usa provider, endpoint, autenticazione e trasporto esistenti. Esamina soltanto gli SSE di risposta nella traccia Codex riconoscibile, se già presente, senza attivare il tracing. Eventi JSONL ordinari, JSON generico, prompt, messaggi dell'agente e risultati dei tool non dimostrano una risposta del server. `http_trace` è esplicita e disponibile per la CLI host: attiva la traccia e configura il provider `chatgpt-http` e il trasporto HTTP. Questo cambia le condizioni sperimentali rispetto al percorso standard: confrontare o combinare le run tenendo conto della differenza. I log di traccia possono contenere dati sensibili e vanno protetti.

Docker Sandbox mantiene il normale proxy OAuth e percorso di esecuzione in `passive`; `http_trace` viene registrata come `unsupported_backend` senza modificare il sandbox. La [documentazione Docker sulle credenziali](https://docs.docker.com/ai/sandboxes/configuration/credentials/) descrive l'autenticazione tramite proxy, non un'interfaccia supportata e non invasiva per ottenere i metadati di sampling. I test simulati non dimostrano la disponibilità su un backend reale. Se i log ordinari non contengono tracce di risposta verificabili, i valori rimangono `null`.

I parametri richiesti dal client, quelli dichiarati dal server e quelli effettivamente applicati dal campionatore sono distinti. Il raccoglitore registra soltanto quelli dichiarati in tracce di risposta riconoscibili; tali dichiarazioni non dimostrano il funzionamento interno del campionatore. Non deduce valori dal modello, dal reasoning effort o da default ipotizzati. I valori devono essere numerici e finiti: temperatura non negativa, top_p in [0, 1]; i limiti specifici del provider vanno verificati separatamente per provider e modello effettivi. Zero è un numero; `null` indica assenza di un valore utilizzabile (celle vuote in CSV/Excel).

`temperature_status` e `top_p_status` sono indipendenti: `observed`, `not_reported`, `explicit_null`, `invalid`, `inconsistent`, `unavailable`, `disabled` o `unsupported_backend`. Lo stato complessivo è `observed` solo se entrambi sono osservati, `partial` se gli stati differiscono, altrimenti riflette lo stato comune o un errore. Sono conservati i valori validi distinti e il conteggio delle risposte; valori discordanti producono uno scalare null e `inconsistent`. Le run storiche conservano i propri campi e sono aggregabili senza inventare stati.

Per un uso scientifico verificare la traccia in `stderr.log`, gli ID di risposta e l'artefatto di telemetria, lo stato di ogni parametro, gli intervalli, la coerenza fra risposte, backend e trasporto, conservando la configurazione sperimentale. Un evento simulato o la sola attivazione della traccia non dimostrano l'acquisizione; la dichiarazione del server non prova il valore interno applicato. In assenza di ID non è possibile deduplicare con certezza. Rigenerare gli aggregati con `python scripts/aggregate_results.py` senza rieseguire gli agenti.

## Aggregazione e report

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

L'aggregatore analizza i file `evaluation/metrics.json` e i report del checker presenti in `runs/`:
- `results/runs.csv`: Una riga per run con identificatori, configurazione, stato, percentuale superamento, tempi, token e hash delle correction.
- `results/checks.csv`: Una riga per ogni singola asserzione verificata dal checker.
- `results/summary.csv`: Statistiche descrittive raggruppate per esperimento, scenario, prompt, modalità skill e modello.
- `results/benchmark.xlsx`: Foglio di lavoro Excel formattato con i fogli `Runs`, `Checks` e `Summary`, corredato da filtri, righe separate per scenario e colonne dimensionate.

## Smoke check

```bash
python scripts/smoke_check.py
```

Lo smoke test convalida staticamente l'intero impianto senza chiamare gli LLM o avviare container:
1. Convalida dipendenze e import (`inspect_ai`, `inspect_swe`, `kathara_lab_checker`, `pandas`, `yaml`, `openai`).
2. Verifica discovery degli scenari e caricamento configurazioni.
3. Verifica il dispatch per entrambi gli agenti (`codex` e `antigravity`).
4. Valida staticamente `docker_sandbox_runner` (nomi univoci, suffissi UUID, parse eventi JSONL, gerarchia eccezioni).
5. Verifica il rifiuto di combinazioni cross-provider non valide (es. `--agent antigravity` con `benchmark.yaml`).
6. Testa la CLI `inspect log dump --header-only` su un log generato.
7. Simula l'allocazione del workspace isolato, il calcolo del diff e l'aggregazione.

## Agent supportati

| Agente | CLI / Tool | File Config | Modello verificato | Autenticazione / Backend |
|---|---|---|---|---|
| Codex | `codex` / `sbx` | `benchmark.yaml` | `gpt-5.6-terra` | Login ChatGPT locale (Host CLI) / Docker Sandbox (`sbx` OAuth proxy) |
| Antigravity | `agy` | `benchmark_antigravity.yaml` | `gemini-3.8-flash` | Login Google locale (Host CLI) |

Entrambi gli agenti condividono i medesimi principi operativi: l'agente configura i file all'interno di un workspace isolato e il Kathara Lab Checker valuta la correction canonica sul laboratorio risultante in modo deterministico, senza alcun intervento dell'LLM nella fase di giudizio.

## Strato Esperimenti (Experiment Layer)

Lo strato esperimenti consente di orchestrare matrici complete di esecuzioni definite in file YAML, preservando la compatibilità con i comandi per singoli scenari.

### Concetti chiave

| Concetto | Significato |
|---|---|
| **scenario** | Laboratorio Kathara con baseline `lab/` e `correction.yaml` |
| **prompt_type** | Variante del prompt (T1–T6) corrispondente a `prompt/<scenario>/<T>.md` |
| **skill_mode** | Modalità skill: `no_skill`, `creation_only`, `dns_only`, `both_forced`, o `auto` |
| **replicate** | Ripetizione statistica pianificata dall'esperimento |
| **run_number** | Contatore fisico progressivo della directory (`rNNN`) |
| **experiment** | Matrice formata da `scenario × prompt × skill_mode × replicate` |

`replicate` e `run_number` coincidono normalmente. Divergono solo se una run fallisce per problemi infrastrutturali e viene ritentata: la nuova run assume un nuovo `run_number` soddisfacendo la medesima `replicate`.

### File YAML dell'Esperimento

Crea una configurazione in `experiments/` (es. `experiments/thesis_final.yaml`):

```yaml
experiment:
  id: thesis_final

scenarios:
  - lab00_five_router
  - lab01_ring6_dual

prompt_types:
  - T1
  - T3

skill_modes:
  - no_skill
  - dns_only

repetitions: 3
```

### Eseguire un esperimento

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml
```

Prima di invocare qualsiasi modello, l'orchestratore valida staticamente l'esistenza di tutti gli scenari, la presenza dei file prompt, le modalità skill, la validità delle correction e i prerequisiti infrastrutturali.

### Ripresa di esperimenti interrotti (`--resume`)

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --resume
```

Con l'opzione `--resume`, l'orchestratore:
1. Esamina le run esistenti associate a `experiment_id`.
2. Identifica le repliche già concluse con `pipeline_state: COMPLETED` e le salta.
3. Esegue unicamente le repliche mancanti o quelle interrotte da errori infrastrutturali (`AUT_FAILED`, `CHECKER_FAILED`).
4. Le run in cui l'agente ha completato l'esecuzione ma non ha superato i check del laboratorio (`task_success: false`) sono osservazioni sperimentali valide e **non** vengono rieseguite.

### Rivalutazione delle correction a livello di esperimento

Per riapplicare una correction aggiornata a tutte le run esistenti senza effettuare chiamate ai modelli e senza spendere token:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction
```

È possibile filtrare a un sottoinsieme specifico:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction \
  --filter-scenario lab00_five_router --filter-prompt T1 --filter-skill-mode dns_only
```

Ogni rivalutazione incrementa il contatore `evaluation_revision` e aggiorna `last_reevaluated_at` nel manifest della run.

### Anteprima del piano (`--dry-run`)

Per visualizzare la matrice pianificata e lo stato di completamento senza eseguire nulla:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --resume --dry-run
```

### Osservazioni Internet e protocollo Skill

Le metriche AUT includono `internet` e `skill_compliance`, indipendenti dal
checker. Si analizzano soltanto gli eventi AUT: ricerche web completate e
strumenti MCP web riconoscibili costituiscono evidenza; i comandi di rete sono
solo candidati, anche se terminano con successo. `shell_network_candidates`
conta gli eventi shell con una destinazione esterna identificabile;
`shell_network_local` e `shell_network_uncertain` riportano separatamente
destinazioni locali e casi non risolti. Il tokenizer shell non esegue espansioni
e può non riconoscere script complessi. `search_result_domains` contiene URL
dei risultati di ricerca; `visited_domains` contiene soltanto domini associati
a pagine aperte con risultati riconoscibili. `external_domains` è mantenuto
per compatibilità e coincide ora con `visited_domains`. Un risultato di ricerca
non prova una visita. Le aperture e le operazioni web di altro tipo non sono
conteggiate come ricerche. Il monitoraggio non è una cattura del traffico:
assenza di eventi, log incompleti e letture native non registrate restano
`null`/`unknown`, non indicano assenza di utilizzo o violazione. La lettura
shell è verificata quando l'output identifica il contenuto della Skill;
comandi senza contenuto riconoscibile restano non verificabili. Antigravity
richiede la Skill DNS anche quando la modalità registrata è `no_skill`.
La policy `restricted` indica il superamento dei controlli sandbox su due
endpoint del modello e due destinazioni esterne: non prova il blocco di ogni
possibile destinazione, né impedisce ricerche web svolte dal provider.

Le percentuali nel Summary sono frazioni: `internet_confirmed_rate` usa tutte
le run del gruppo, incluse quelle sconosciute; `internet_observed_rate` è
un alias esplicito della stessa proporzione osservata, non una stima della
percentuale effettiva. `skill_compliance_rate` usa le
run con letture obbligatorie note, incluse quelle non verificabili. Il
contatore `web_search_calls_denominator` indica il numero di trace non vuote
usate per la media delle ricerche osservate; i log parziali possono sottostimarla.
I dati storici senza nuove metriche rimangono vuoti fino alla ricostruzione:

```bash
.venv/bin/python scripts/backfill_observations.py --dry-run
.venv/bin/python scripts/backfill_observations.py
.venv/bin/python scripts/aggregate_results.py
.venv/bin/python -m pytest -q
```

Il backfill non avvia AUT, Kathara o checker e non modifica i laboratori;
in caso di eccezione ripristina i file di metriche e report preesistenti
tramite copie in memoria; non garantisce il ripristino dopo interruzioni
brusche del processo o della macchina.
Per una prova isolata usare `--runs` e `--output` su copie dei dati.

### Protocollo di lettura Skill v2

Le nuove run Codex registrano `skill_protocol: explicit_read_v2`; le run
storiche conservano il protocollo indicato nel loro manifest. Le modalità e la
preparazione delle Skill restano invariate. Nelle modalità forzate la direttiva
chiede all'agente una lettura integrale dedicata per ogni Skill prima delle
modifiche. Il runner non legge la Skill al posto dell'agente. Antigravity
mantiene la propria direttiva DNS e il proprio protocollo non versionato.

`skill_details` distingue tentativo, contenuto identificato, lettura completa,
ordine e obbligatorietà per ciascuna Skill. La lettura completa richiede un
confronto con l'hash SHA-256 della Skill registrato nel manifest: si confronta
l'output completo oppure, se la copia canonica attuale ha lo stesso hash,
il suo contenuto integrale con l'output. Letture in blocchi `sed` consecutivi
possono essere ricostruite e confrontate con l'hash. In assenza dell'hash o
in caso di output troncato la completezza resta non verificabile. Una copia
locale della Skill serve solo come riferimento di confronto: non dimostra una
lettura da parte dell'agente.

L'ordine è una verifica **a posteriori** rispetto alla prima modifica
riconoscibile nei log AUT; operazioni sovrapposte, senza evento iniziale o
modifiche non visibili possono renderlo non verificabile. Una lettura completa
senza modifiche osservate non prova l'ordine. `strict_status` e
`protocol_compliance_observed` includono per v2 anche la richiesta di
operazioni dedicate. L'assenza di prove non è una violazione dimostrata.
Il vecchio `required_reads_observed` continua a indicare la precedente prova
di contenuto identificato, non la lettura integrale; i nuovi campi e le nuove
colonne `strict_*` indicano la verifica più rigorosa. Il denominatore di
`strict_observed_compliance_rate` è il numero di run del gruppo con Skill
obbligatorie, incluse quelle non verificabili. Il raggruppamento Summary
include `skill_protocol`, per mantenere separati v1 e v2.
