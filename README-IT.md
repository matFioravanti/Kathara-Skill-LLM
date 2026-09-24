# Kathara Skill LLM Benchmark

Benchmark riproducibile per valutare agenti LLM CLI che configurano DNS e servizi web in laboratori Kathara. Gli agenti supportati sono **Codex CLI** e **Antigravity CLI (agy)**, ciascuno con autenticazione rigorosamente locale.

## Architettura

Ogni scenario contiene soltanto un prompt e un laboratorio iniziale immutabile. Per ciascuna modalità Skill il runner alloca una run in `runs/<scenario>/<skill_mode>/rNNN`, conserva il baseline in `input/lab`, crea la copia modificabile in `lab` e avvia l'Agent Under Test (AUT) sul Mac host. I numeri delle run avanzano indipendentemente per scenario e modalità.

L'**active agent** di una run è unico: lo stesso agente viene utilizzato sia come AUT sia come Correction Generator. Non è possibile combinare agenti diversi nella stessa run.

Terminata l'esecuzione AUT, il runner salva gli eventi, chiude la finestra di misurazione e calcola il diff rispetto al laboratorio originale. Il Kathara Lab Checker valuta poi il `lab/` di quella run usando la correction manuale canonica `corrections/<scenario>/correction.yaml`. Una copia byte per byte viene salvata in `evaluation/correction.yaml` per riprodurre la valutazione.

Il risultato finale deriva esclusivamente dal checker. Un'esecuzione AUT riuscita può quindi avere `aut_execution_success=true`, `checker_execution_success=true` e `task_success=false`. Se la correction o il checker falliscono per un problema infrastrutturale, `task_success` rimane nullo.

```text
Prompt + Skill
      │
      ▼
Codex / Antigravity CLI
      │
      ├── result.json
      └── events.jsonl
              │
              ▼
        Inspect Adapter
              │
              └── run_id.eval

Laboratorio generato
      │
      ▼
corrections/<scenario>/correction.yaml
      │
      ▼
evaluation/correction.yaml → Kathara Lab Checker
      │
      └── checker results

run_id.eval ───────┐
                   ├── aggregation ──► runs.csv / checks.csv / summary.csv
checker results ───┘
```

### Backend Codex

`codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` esegue Codex senza API key, passa il prompt via stdin e conserva tutti gli eventi JSONL.

### Backend Antigravity

`agy --add-dir <workspace> --dangerously-skip-permissions --output-format stream-json --model <model> --effort <effort> --print <prompt>` esegue Antigravity con autenticazione locale Google.

### Telemetria Inspect AI

Al termine dell'AUT, un adapter dedicato legge `result.json` ed `events.jsonl` e costruisce un file di log nativo Inspect AI (`runs/<scenario>/<skill_mode>/rNNN/logs/aut/<scenario>__<skill_mode>__rNNN.eval`). Il log registra input/output tokens, reasoning tokens, `input_tokens_cache_read`, durata, tool calls, errori e metadata della run. Il file è ispezionabile con `inspect log dump` o `read_eval_log`.

Inspect AI opera esclusivamente come sistema di telemetria: non avvolge la CLI dell'AUT, non legge, genera o influenza `correction.yaml`, e non partecipa alla valutazione del laboratorio. Kathara Lab Checker determina il superamento dei check in modo totalmente deterministico. I due sistemi rimangono separati e vengono associati solo in fase di aggregazione tramite l'identificatore univoco `run_id`.

## Requisiti e installazione

Servono Python 3.11 o successivo, Docker con daemon attivo e Kathara. In aggiunta, in base all'agente scelto:

* **Codex**: Codex CLI installata e autenticata con ChatGPT (`codex --version`, `codex login status`).
* **Antigravity**: Antigravity CLI installata con autenticazione locale Google (`agy --version`).

Non è necessario avere entrambi installati: il preflight verifica solo i prerequisiti dell'agente configurato.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` è il freeze dell'ambiente risolto. Le versioni centrali sono Inspect AI 0.3.266, Inspect SWE 0.2.71, kathara-lab-checker 0.1.14, Kathara 3.8.3, pandas 3.0.6 e PyYAML 6.0.3.

Non impostare `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY` o `INSPECT_EVAL_MODEL`: il runner le rimuove soltanto dalla copia dell'environment passata al subprocess, senza modificare l'ambiente dell'utente.

## Configurazione

Ogni agente ha il proprio file di configurazione dedicato:

* `benchmark.yaml` — configurazione **Codex** (`gpt-5.6-terra`, reasoning effort `low`)
* `benchmark_antigravity.yaml` — configurazione **Antigravity** (`gemini-3.8-flash`, reasoning effort `low`)

L'agente è determinato dal campo `aut.agent` nel file di configurazione. Il flag `--agent` sulla CLI serve esclusivamente come verifica di coerenza: deve coincidere con `aut.agent` nel YAML, altrimenti il comando viene rifiutato. L'override cross-provider non è supportato.

Ogni scenario ha una correction manuale in `corrections/<scenario>/correction.yaml`, condivisa da tutti gli agenti, le modalità Skill e le ripetizioni dello scenario. Il preflight ne verifica presenza e validità prima di qualsiasi run modello; l'AUT non può leggerla. Il checker riceve esplicitamente il `lab/` della run e lo snapshot della correction.

## Skill richieste

Il repository predispone le directory ma non inventa il contenuto delle Skill o delle correction, che deve essere fornito dall'esperimento:

```text
skills/kathara-creation/SKILL.md
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
corrections/<scenario>/correction.yaml
```

La Creation Skill deve dichiarare `name: kathara-creation` e la DNS Skill `name: kathara-dns`; entrambe richiedono il campo `description`. Il contenuto della Creation Skill è fornito dall'esperimento. La skill checker e lo schema possono essere usati per scrivere le correction, ma il benchmark non esegue più un agente per generarle. Per verificare la DNS Skill:

```bash
python scripts/run_benchmark.py --check-skills
```

L'assenza delle Skill runtime o della correction di uno scenario produce un errore esplicito prima di qualsiasi chiamata modello.

Gli esperimenti Codex selezionano una modalità Skill con `--skill-mode`:

| Modalità | Disponibili a Codex | Richieste esplicitamente |
|----------|---------------------|-------------------------|
| `no_skill` | nessuna | nessuna |
| `creation_only` | Creation | Creation |
| `dns_only` | DNS | DNS |
| `both_forced` | Creation e DNS | entrambe |
| `auto` | Creation e DNS | nessuna |

La modalità predefinita è `dns_only`, come nel comportamento Codex precedente. Ogni run riceve solo le skill selezionate sotto `lab/.codex/skills/`. Copie omonime nello scope utente o nei parent interrompono il preflight per evitare run contaminate. Le modalità che includono Creation richiedono il file canonico `skills/kathara-creation/SKILL.md`.

`--skill-mode all` orchestra in sequenza le cinque modalità sopra. Prima verifica tutte le skill necessarie, poi crea una run indipendente per ogni modalità nell'ordine indicato. Il manifest di ogni run riporta la modalità effettiva.

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --agent codex --skill-mode auto
```

## Scenari

Gli scenari vengono scoperti automaticamente sotto `scenarios/` e sono validi quando contengono:

```text
scenarios/<scenario_id>/
├── prompt.txt
└── lab/
    └── lab.conf
```

Non aggiungere `scenario.yaml` né una correction dentro lo scenario. Il prompt è la fonte normativa; `lab/` è copiato per ogni run e non viene modificato. La correction manuale va in `corrections/<scenario>/correction.yaml`.

## Esecuzione

Assicurati di aver attivato l'ambiente virtuale prima di eseguire qualsiasi comando:

```bash
source .venv/bin/activate
```

Il preflight controlla skill, dipendenze dell'agente configurato, Docker, Compose, Kathara e checker senza fare chiamate al modello. Verifica solo l'agente specificato nel file di configurazione:

```bash
# Preflight Codex (non richiede agy)
python scripts/run_benchmark.py --preflight --agent codex

# Preflight Antigravity (non richiede codex)
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --preflight --agent antigravity
```

Eseguire uno scenario:

```bash
# Con Codex
python scripts/run_benchmark.py --scenario example_dns_001 --agent codex

# Con Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --scenario example_dns_001 --agent antigravity
```

Eseguire cinque ripetizioni di tutti gli scenari:

```bash
# Con Codex
python scripts/run_benchmark.py --all --repetitions 5 --agent codex

# Con Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --all --repetitions 5 --agent antigravity
```

`benchmark.continue_on_error` decide se continuare dopo una run infrastrutturalmente fallita. Una soluzione AUT valutata e bocciata dal checker è una run completata, non un errore del comando.

## Artefatti e stati

Ogni run usa un ID logico leggibile, per esempio `example_dns_001__dns_only__r001`, e conserva:

```text
runs/<scenario>/<skill_mode>/rNNN/
├── manifest.json
├── input/
│   ├── lab/          # baseline originale immutabile
│   └── prompt.md
├── lab/              # unica copia modificabile — before → after AUT
├── evaluation/
│   ├── correction.yaml  # snapshot dell'input di valutazione canonico
│   └── metrics.json     # metriche elaborate e normalizzate della run
├── results/          # report CSV del checker
└── logs/
    ├── aut/          # events.jsonl, stderr.log, result.json, invocation.json, prompt.txt, <scenario>__<skill_mode>__rNNN.eval
    ├── diff.json
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

`manifest.json` registra identificatori, timestamp, versioni, hash delle skill, stato e riferimenti agli artefatti. Registra la correction canonica, il suo digest SHA-256 e il percorso dello snapshot fornito al checker.

`runs/` è la fonte persistente. Ogni run conserva i dati elaborati in `evaluation/metrics.json`, insieme alla trace originale dell'agente e ai report del checker. `results/` contiene esattamente tre CSV derivati:

* `runs.csv` — una riga per run con skill selezionate, stato, tempi, token, conteggi checker e digest della correction.
* `checks.csv` — una riga per ogni test individuale del Kathara Lab Checker.
* `summary.csv` — statistiche descrittive raggruppate per scenario e modalità Skill.

I token provengono dall'ultimo evento Codex `turn.completed` che contiene `usage` in `logs/aut/events.jsonl`. La trace corrente espone `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens` e `reasoning_output_tokens`; `total_tokens` resta null se assente. Gli usage dei turni precedenti non vengono sommati. `selected_skills` contiene soltanto Skill disponibili il cui `SKILL.md` compare in un comando di lettura `command_execution` tracciato; il dato resta distinto dalle Skill forzate.

`agent_seconds` viene dalla durata del subprocess misurata dal runner AUT. `checker_seconds` misura `run_checker`, inclusi preparazione e parsing dei report. `total_seconds` misura il tempo da subito prima dell'allocazione del workspace fino al completamento delle fasi della run; esclude preflight e serializzazione finale delle metriche. In `summary.csv`, `skill_selection_rate` è valorizzato solo per `auto`: il denominatore include le run AUT completate con trace leggibile e il numeratore quelle che hanno selezionato almeno una Skill disponibile.

## Aggregazione e analisi

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

L'aggregatore legge soltanto le run nel formato `scenario/skill_mode/rNNN/evaluation/metrics.json` e i report checker già salvati. Non avvia Codex, Docker, Kathara o il checker e può essere rilanciato con `python scripts/aggregate_results.py`. Scrive `runs.csv`, `checks.csv` e `summary.csv`, più `benchmark.xlsx` con i fogli `Runs`, `Checks` e `Summary`. Il workbook raggruppa le righe per scenario con linee di separazione, intestazioni formattate, filtri e larghezze colonna adatte ai contenuti; gli altri file in `results/` restano intatti.

## Smoke check

```bash
python scripts/smoke_check.py
```

Lo smoke check convalida staticamente entrambi gli agent (`codex` e `antigravity`), verifica il dispatch AUT, testa il rifiuto dell'override cross-provider (`--agent antigravity` con `benchmark.yaml` e viceversa), e simula aggregazione e diff senza interagire con gli LLM.

## Agent supportati

| Agent | CLI | Config file | Modello verificato | Auth |
|-------|-----|-------------|-------------------|------|
| Codex | `codex` | `benchmark.yaml` | `gpt-5.6-terra` | ChatGPT login locale |
| Antigravity | `agy` | `benchmark_antigravity.yaml` | `gemini-3.8-flash` | Google login locale |

Entrambi gli agenti condividono la stessa architettura: l'agente altera i file del laboratorio invocato su linea di comando, genera la correction, e il Kathara Lab Checker determina il risultato finale senza alcun coinvolgimento dell'LLM nella valutazione.
