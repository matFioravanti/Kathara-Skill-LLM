# Kathara-Skill-LLM — benchmark DNS su laboratori Kathara

Il progetto valuta il comportamento di agenti LLM nella configurazione di servizi DNS su **laboratori Kathara preesistenti**, utilizzando un correttore manuale (`correction.yaml`) e il Kathara Lab Checker. Ogni esecuzione conserva la baseline, il prompt inviato, la soluzione prodotta dall'agente e le metriche di valutazione. Sono supportati gli agenti Codex e Antigravity; le cinque modalità Skill Codex sono descritte più avanti.

## Stato del benchmark e ambito attuale

**La fase operativa corrente usa esclusivamente l'albero DNS `base`.** Le directory `aster`, `aurora` e `meridian` sono predisposte per esperimenti futuri, ma non devono essere incluse nelle esecuzioni Base e non richiedono ancora correction.

I laboratori contengono **solo la rete IPv4 con routing statico**: la configurazione DNS è il compito assegnato all'agente, non è già presente nella baseline.

| Lab | Livello | Router | PC | LAN | Zone DNS autoritative | Deleghe |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `lab_01` | `small` | 4 | 20 | 6 | 13 | 12 |
| `lab_02` | `medium` | 8 | 40 | 10 | 31 | 30 |
| `lab_03` | `large` | 12 | 60 | 15 | 49 | 48 |

Ogni laboratorio ha la propria `lab.conf`, i file `<device>.startup` per gli apparati e **una correction Base per livello**, indipendente da tipo di prompt, modalità Skill e replica.

## Struttura delle risorse

```text
scenarios/
  lab_01/
    lab/                                # lab.conf + *.startup, baseline DNS-free
    tasks/base/small/correction.yaml
  lab_02/
    lab/
    tasks/base/medium/correction.yaml
  lab_03/
    lab/
    tasks/base/large/correction.yaml

prompt/
  base/
    small/                              # 6 formulazioni, 01/04/07/10/13/16
    medium/                             # 6 formulazioni, 02/05/08/11/14/17
    large/                              # 6 formulazioni, 03/06/09/12/15/18

experiments/
  quick_test.yaml                       # una run: lab_01/base/small/T1/dns_only
  thesis_final.yaml                     # matrice completa Base

runs/
  <experiment_id>/<lab_id>/<dns_tree_id>/<task_level>/<prompt_type>/<skill_mode>/rNNN/
results/
  runs.csv
  checks.csv
  summary.csv
  benchmark.xlsx
```

Le cartelle `tasks/aster`, `tasks/aurora` e `tasks/meridian` possono rimanere vuote: sono riservate a correction specifiche da creare solo quando si deciderà di testare tali alberi. **Non copiare automaticamente la correction `base`**, perché gli altri alberi prevedono nomi di zone e assegnazioni di macchine differenti.

### Identificazione dei sei tipi di prompt

I prompt sono in `prompt/<dns_tree_id>/<task_level>/` e usano **nomi descrittivi**. Il runner risolve automaticamente i file per tipo (T1–T6) e livello; mantiene un fallback al vecchio formato `T1.md`–`T6.md` per fixture e dati legacy.

| Tipo | Categoria | Small | Medium | Large |
| --- | --- | --- | --- | --- |
| T1 | `technical_structured` | `01_technical_structured_small.md` | `02_technical_structured_medium.md` | `03_technical_structured_large.md` |
| T2 | `technical_discursive` | `04_technical_discursive_small.md` | `05_technical_discursive_medium.md` | `06_technical_discursive_large.md` |
| T3 | `nontechnical_discursive` | `07_nontechnical_discursive_small.md` | `08_nontechnical_discursive_medium.md` | `09_nontechnical_discursive_large.md` |
| T4 | `nontechnical_unstructured` | `10_nontechnical_unstructured_small.md` | `11_nontechnical_unstructured_medium.md` | `12_nontechnical_unstructured_large.md` |
| T5 | `graphical_tree` | `13_graphical_tree_small.md` | `14_graphical_tree_medium.md` | `15_graphical_tree_large.md` |
| T6 | `json_structured` | `16_json_structured_small.md` | `17_json_structured_medium.md` | `18_json_structured_large.md` |

Ogni gruppo di sei prompt descrive un compito DNS da valutare con **la stessa correction** del laboratorio e dell'albero. Il sistema controlla l'esistenza e la leggibilità delle risorse; la corrispondenza semantica completa tra tutte le formulazioni resta una proprietà da verificare nell'analisi sperimentale.

### Correction e valutazione

Le correction Base si trovano nei tre percorsi indicati sopra. Contengono controlli sulla topologia, sugli IP, sulle rotte statiche e sulle proprietà DNS attese: server autoritativi, resolver, record e verifiche mediante comandi, inclusi test su SOA, deleghe/NS, record A/MX e risoluzione dai client.

Il runner legge la correction **prima** di invocare l'agente, ne conserva una copia in `evaluation/correction.yaml` ed esegue il Kathara Lab Checker **dopo** la generazione della soluzione. La correction non viene esposta nel workspace modificabile dell'agente.

## Requisiti e ambiente

- Python e dipendenze presenti in `requirements.txt` (inclusi `kathara` e `kathara_lab_checker`).
- Docker e Kathara funzionanti sull'host, necessari per le esecuzioni effettive.
- CLI dell'agente configurato e autenticata localmente.
- Per il backend Codex attualmente configurato in `benchmark.yaml`: Docker Sandboxes (`sbx`), con disponibilità di daemon e autenticazione Codex nel sandbox.

Preparazione dell'ambiente virtuale:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Il file `benchmark.yaml` contiene l'agente, il modello, il backend di esecuzione, le Skill, i timeout e le impostazioni del checker. Non occorre modificare i laboratori o le correction per selezionare un esperimento.

## Esperimenti configurati

### `experiments/quick_test.yaml`

Esegue **una sola run** con:

- `lab_01`, `base`, `small`
- prompt `T1`
- modalità Skill `dns_only`
- `repetitions: 1`

### `experiments/thesis_final.yaml`

Contiene le tre assegnazioni `lab_01/base/small`, `lab_02/base/medium` e `lab_03/base/large`, con `T1`–`T6` e cinque modalità Codex (`no_skill`, `creation_only`, `dns_only`, `both_forced`, `auto`).

Con la ripetizione attualmente configurata, l'esperimento completo prevede **3 laboratori × 6 prompt × 5 modalità × 1 replica = 90 run**. Le modalità descrivono condizioni sperimentali già implementate nel repository; il lavoro sulle risorse Kathara del progetto segue le Skill specializzate.

## Come eseguire i test

Eseguire i comandi dalla **radice del repository**, con l'ambiente virtuale attivo.

**1. Test automatici del repository:**

```bash
python -m pytest -q
```

**2. Verifica statica del quick test (senza avviare agenti o Kathara):**

```bash
python scripts/run_experiment.py experiments/quick_test.yaml --dry-run
```

**3. Prima esecuzione completa di prova:**

```bash
python scripts/run_experiment.py experiments/quick_test.yaml
```

**4. Visualizzazione della matrice Base (90 run, senza eseguirle):**

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --dry-run
```

**5. Avvio del benchmark completo:**

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml
```

È possibile limitare la matrice a un singolo caso, per esempio Lab 02/T3 con Skill DNS:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml \
  --lab lab_02 --dns-tree base --task-level medium \
  --prompt-type T3 --skill-mode dns_only --dry-run
```

Rimuovere `--dry-run` solo quando si intende eseguire la run. I comandi di ripresa o rivalutazione sono:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --resume
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction --dry-run
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction
```

`--resume` evita di ripetere osservazioni già completate; `--rerun-correction` rivaluta run già presenti senza rilanciare l'agente. Si possono usare i filtri `--lab`, `--dns-tree`, `--task-level`, `--prompt-type` e `--skill-mode`.

Il runner `scripts/run_benchmark.py` può delegare all'interfaccia attuale usando `--experiment`, ma **per i nuovi esperimenti Base è consigliato `scripts/run_experiment.py`**. Le opzioni legacy basate su `--scenario` e `--all` senza un experiment non descrivono questa struttura di correction.

## Risultati e riproducibilità

Ogni run ha la propria directory sotto `runs/<experiment_id>/<lab_id>/<dns_tree_id>/<task_level>/<prompt_type>/<skill_mode>/rNNN/` e conserva, tra gli altri, `manifest.json`, `input/lab/`, `input/prompt.md`, `lab/`, i log dell'agente e `evaluation/correction.yaml`.

L'aggregazione produce `results/runs.csv`, `results/checks.csv`, `results/summary.csv` e `results/benchmark.xlsx`. Lo stato dell'esecuzione (`pipeline_state`) va distinto dall'esito funzionale (`task_success`): una run `COMPLETED` può correttamente avere `task_success: false`.

## Estensioni future

Il catalogo ammette anche `aster`, `aurora` e `meridian`, ma la fase Base non li usa. Per abilitarli serviranno correction coerenti con i relativi prompt e assegnazioni esplicite negli YAML degli esperimenti; non è necessario modificare la rete di partenza per questo scopo.

I binding facoltativi in `tasks/<dns_tree_id>/<task_level>/bindings.yaml` permettono di sostituire nei prompt `{{server.device}}` e `{{server.address}}`; la risoluzione valida il dispositivo e l'indirizzo rispetto a `lab.conf` e al relativo `.startup`.

---

## Documentazione storica: runner legacy e componenti avanzati

> **Attenzione:** la sezione seguente è conservata come riferimento per l'interfaccia legacy e per dettagli su backend, telemetria, Skill e report. Alcuni esempi e percorsi qui sotto usano il vecchio formato `scenarios/<scenario>/correction.yaml`, `prompt/<scenario>/T1.md` o esperimenti basati su `scenarios:`. **Per i laboratori Base correnti seguire esclusivamente le sezioni aggiornate qui sopra.**

### Kathara Skill LLM Benchmark (archivio)


Reproducible benchmark for evaluating CLI LLM agents that configure DNS and web services in Kathara network emulation laboratories. The supported agents are **Codex CLI** and **Antigravity CLI (agy)**, each using strictly local authentication. Codex additionally supports fully isolated execution inside ephemeral **Docker Sandboxes (`sbx`)**.

## Architecture

Each scenario contains a task prompt, an immutable baseline lab, and a canonical manual correction. For each skill mode, the benchmark runner allocates an independent run directory at `runs/<scenario>/<prompt_type>/<skill_mode>/rNNN`, preserves the original baseline in `input/lab`, provisions the editable workspace copy in `lab`, and executes the Agent Under Test (AUT). Run numbers advance independently for each scenario and skill mode.

The **active agent** of a run is unique: the configured agent acts as the AUT. Combining different agents within the same run is not supported.

After AUT execution terminates (whether successfully, on timeout, or on error), the runner closes the measurement window, persists telemetry events, stages the resulting files, and computes the diff against the original baseline. The Kathara Lab Checker then evaluates the generated `lab/` using the canonical manual correction at `scenarios/<scenario>/correction.yaml`. A byte-for-byte snapshot is stored in `evaluation/correction.yaml` for complete evaluation reproducibility. The correction remains strictly outside `lab/` and is never exposed to the AUT.

Final task correctness is determined exclusively by the checker:
- A completed run may have `aut_execution_success=true`, `checker_execution_success=true`, and `task_success=false`.
- If an infrastructure or technical error occurs during AUT execution or checking, `task_success` remains `null` and the run is marked with an appropriate pipeline error state (`AUT_FAILED`, `CHECKER_FAILED`, etc.).

```text
Prompt + Skill
      │
      ▼
AUT Execution Backend
  ├─ Host CLI: Codex / Antigravity CLI
  └─ Docker Sandbox (sbx): Ephemeral Container
      │
      ├── result.json
      ├── events.jsonl
      └── sandbox_metadata.json (sbx)
              │
              ▼
        Inspect Adapter
              │
              └── run_id.eval (Guaranteed Inspect AI log)

Generated Lab (lab/)
      │
      ▼
scenarios/<scenario>/correction.yaml
      │
      ▼
evaluation/correction.yaml ──► Kathara Lab Checker
                                      │
                                      └── Checker Reports (CSV)

run_id.eval ────────┐
                    ├── aggregation ──► runs.csv / checks.csv / summary.csv / benchmark.xlsx
checker results ────┘
```

### Codex Execution Backends

Codex supports two execution backends, selectable via `benchmark.yaml`:

1. **Host CLI Backend** (`execution_backend: codex_cli` or omitted):
   Executes `codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` directly on the host machine in an isolated temporary directory, streaming the prompt via stdin and capturing all JSONL events.
2. **Docker Sandbox (`sbx`) Backend** (`execution_backend: docker_sandbox`):
   Executes Codex inside a disposable, single-use sandbox container managed by Docker Sandboxes (`sbx` v0.48.0).
   - **Ephemeral Lifecycle**: Each run provisions a dedicated sandbox with a unique name (`kathara-<scenario>-r<repetition>-<uuid8>`) using `sbx create` with `--skills=off`. On completion (success, crash, timeout, or cancellation), the sandbox is forcefully removed with `sbx rm --force` (with retries). If sandbox removal fails, the run is flagged with `SandboxCleanupError`.
   - **Direct Lab Bind-Mount**: The temporary lab workspace is mounted directly into the container. All modifications made by Codex are written immediately to disk without requiring `sbx cp`.
   - **Zero Host Credential Exposure**: Authenticates solely through the official Docker Sandboxes OAuth proxy / token mechanism. Host credential files are never mounted into the container.
   - **Strict Egress Network Policy**: Network access is restricted to authorized OpenAI OAuth and model API endpoints. Unauthorized egress is denied.
   - **Memory Explicitly Disabled**: Codex internal persistent memory is disabled across flags and configuration options (`--disable memories`, `-c memories=false`, `-c memories.use_memories=false`, `-c memories.generate_memories=false`, `-c features.memories=false`) to eliminate state contamination across runs.
   - **Host Checker Isolation**: Kathara and the Kathara Lab Checker remain strictly on the host and are never mounted into or invoked from the sandbox.
   - **No Silent Fallback**: Technical failures within the sandbox never trigger a silent fallback to host execution.

### Antigravity Backend

`agy --add-dir <workspace> --dangerously-skip-permissions --output-format stream-json --model <model> --effort <effort> --print <prompt>` executes Antigravity CLI with local Google authentication in an isolated workspace.

### Inspect AI Telemetry & Error Hardening

Following AUT execution, a dedicated telemetry adapter reads `result.json`, `events.jsonl`, and sandbox metadata to construct a native Inspect AI evaluation log:
```text
runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/logs/aut/<scenario>__<prompt_type>__<skill_mode>__rNNN.eval
```
The log records input/output tokens, reasoning tokens, cache tokens, duration, tool calls, failure diagnostics, and run metadata. It can be inspected with `inspect log dump` or `read_eval_log`.

Inspect AI operates strictly as an observational telemetry system: it does not wrap the AUT process, does not generate or modify `correction.yaml`, and does not participate in scoring the lab.

**Resilience & Failure Diagnostics:**
- **Guaranteed Log Generation**: The native `.eval` log is guaranteed to be created even when the AUT process times out, crashes, or fails during synchronization, preserving failure diagnostics and event traces.
- **Partial Diff Preservation**: Lab synchronization uses a staged transfer (`lab.sync-tmp` -> `lab`). If the AUT is interrupted after modifying partial configuration files, the changes are retained and captured in `logs/diff.json`.
- **Diagnostic Tracing**: Infrastructure failures record error messages and stack traces in `logs/pipeline_error.log`, `manifest.json`, and `evaluation/metrics.json` under `pipeline_error` and `sandbox` diagnostics.

## Requirements and Installation

- **Python**: 3.11 or later
- **Docker**: Docker daemon running (Docker Desktop on macOS)
- **Kathara**: Network emulation framework installed and operational
- **Agent Prerequisites** (verify only the configured agent):
  - **Codex (Host)**: Codex CLI installed and authenticated (`codex --version`, `codex login status`).
  - **Codex (Docker Sandbox)**: Docker Sandboxes CLI installed (`sbx version` v0.48.0), sbx daemon running or auto-start enabled, and Codex authenticated inside the template container.
  - **Antigravity**: Antigravity CLI installed with local Google login (`agy --version`).

Setup virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` is the pinned specification of the tested environment:
Inspect AI 0.3.266, Inspect SWE 0.2.71, kathara-lab-checker 0.1.14, Kathara 3.8.3, pandas 3.0.6, PyYAML 6.0.3, and openai 3.16.2.

Do not set `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY`, or `INSPECT_EVAL_MODEL`: the runner strips these from the subprocess environment to enforce local authentication.

## Configuration

Each agent has a dedicated configuration file:

* `benchmark.yaml` — **Codex** configuration (`gpt-5.6-terra`, reasoning effort `low`)
* `benchmark_antigravity.yaml` — **Antigravity** configuration (`gemini-3.8-flash`, reasoning effort `low`)

The active agent is defined by `aut.agent` in the configuration file. The `--agent` CLI flag acts as a strict consistency check: it must match `aut.agent` in the YAML, otherwise the command is rejected.

### Docker Sandbox Configuration (`benchmark.yaml`)

When using Codex, the `docker_sandbox` block configures the sbx backend:

```yaml
docker_sandbox:
  execution_backend: docker_sandbox  # "docker_sandbox" to enable sbx; omit/other for host CLI
  sbx_version: "0.48.0"              # expected sbx version (EXPECTED_SBX_VERSION)
  codex_version: "0.149.1"           # expected codex version inside sandbox template
  auto_start_daemon: true            # automatically start sbx daemon if stopped
  auto_start_docker: true            # automatically launch Docker Desktop on macOS if down
  daemon_wait_seconds: 30            # wait timeout after starting sbx daemon
  docker_wait_seconds: 45            # wait timeout after starting Docker Desktop
  cleanup_on_error: true             # always remove container even on error
  verify_sandbox_codex: true         # check codex version & login inside sandbox during preflight
```

### Scenario Corrections

Each scenario maintains one canonical manual correction at `scenarios/<scenario>/correction.yaml`, shared across all agents, skill modes, and replicates. The preflight check validates its existence and syntax before launching model calls. The correction is never copied into `lab/` or exposed to the AUT.

## Required Skills

The repository expects skill definitions under `skills/`:

```text
skills/kathara-creation/SKILL.md
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
scenarios/<scenario>/correction.yaml
```

The Creation Skill must specify `name: kathara-creation`, and the DNS Skill must specify `name: kathara-dns`; both require a `description` frontmatter field. To verify skills without running a benchmark:

```bash
python scripts/run_benchmark.py --check-skills
```

### Skill Modes (Codex)

Codex runs select one of five skill modes via `--skill-mode`:

| Mode | Available Skills | Prompt Directive |
|---|---|---|
| `no_skill` | None | None |
| `creation_only` | Creation (`kathara-creation`) | `$kathara-creation` |
| `dns_only` | DNS (`kathara-dns`) | `$kathara-dns` |
| `both_forced` | Creation + DNS | Both |
| `auto` | Creation + DNS | None (autonomous discovery) |

### Skill Protocol

The benchmark implements the `explicit_read_v1` protocol for Codex:
- In forced modes (`creation_only`, `dns_only`, `both_forced`), the runner injects a standardized, explicit instruction requesting the agent to read the corresponding `SKILL.md` alongside the `$skill` directive.
- In `auto` mode, skills are placed in `lab/.codex/skills/` without prompt injection, testing native skill discovery.
- In `no_skill` mode, no skill directories are provisioned.

The benchmark logs the exact treatment:
- `skill_mode`
- `available_skills`
- `forced_skills`
- `skill_protocol`

The runner does not attempt to infer skill adherence from shell commands, as native skill loading may be unobservable in command execution traces. Final task success is evaluated independently by Kathara Lab Checker.

Run all skill modes sequentially:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --all-skill-modes
```

Reevaluate existing runs in place using updated canonical corrections without consuming LLM tokens:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --rerun-correction
```

## Scenarios

Scenarios are automatically discovered under `scenarios/`:

```text
scenarios/<scenario_id>/
├── correction.yaml
├── metadata.yaml        # Optional metadata (topology, difficulty)
└── lab/
    └── lab.conf
```

Prompts reside exclusively under `prompt/<scenario_id>/<prompt_type>.md` (T1–T6).

```bash
# Run a specific scenario with a prompt type
python scripts/run_benchmark.py --scenario static-routing-5routers --prompt-type T1 --skill-mode dns_only

# Run all five skill modes for a scenario
python scripts/run_benchmark.py --scenario static-routing-5routers --prompt-type T1 --all-skill-modes

# Run all scenarios with 5 repetitions across all skill modes
python scripts/run_benchmark.py --all --prompt-type T1 --all-skill-modes --repetitions 5
```

## Execution

Activate the virtual environment before executing commands:

```bash
source .venv/bin/activate
```

### Preflight Verification

The preflight check verifies skills, agent authentication, Docker, Compose, Kathara, and the checker without consuming model tokens:

```bash
# Codex preflight (validates host CLI or Docker Sandbox sbx according to benchmark.yaml)
python scripts/run_benchmark.py --preflight --agent codex

# Antigravity preflight
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --preflight --agent antigravity
```

### Executing Runs

```bash
# Run single scenario with Codex
python scripts/run_benchmark.py --scenario example_dns_001 --prompt-type T1 --agent codex

# Run single scenario with Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --scenario example_dns_001 --prompt-type T1 --agent antigravity
```

The configuration setting `benchmark.continue_on_error` controls whether the runner proceeds after an infrastructure failure. An AUT solution evaluated and rejected by the checker is considered a successfully completed run, not an error.

## Artifacts and States

Each run preserves a full record under `runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/`:

```text
runs/<scenario>/<prompt_type>/<skill_mode>/rNNN/
├── manifest.json
├── input/
│   ├── lab/                  # Immutable baseline snapshot
│   └── prompt.md
├── lab/                      # Modified lab after AUT execution
├── evaluation/
│   ├── correction.yaml       # Snapshot of canonical evaluation input
│   └── metrics.json          # Normalized metrics for this run
├── results/                  # Kathara Lab Checker CSV reports
└── logs/
    ├── aut/                  # events.jsonl, result.json, invocation.json, prompt_sent.md,
    │                         # sandbox_metadata.json (sbx), <run_id>.eval
    ├── diff.json             # Computed lab diff against input baseline
    ├── pipeline_error.log    # Error traceback (on infrastructure failure)
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

### Metadata and Metrics

- **`manifest.json`**: Captures timestamps, versions (`codex_host_version`, `codex_sandbox_version`, `sbx_version`), execution backend (`codex_cli` vs `docker_sandbox`), sandbox metadata (`sandbox_name`, `sandbox_id`, `sandbox_cleanup_ok`), SHA-256 hashes of prompts, skills, and corrections, and state history.
- **`evaluation/metrics.json`**: Normalized metric record containing status (`COMPLETED`, `AUT_FAILED`, `CHECKER_FAILED`), agent success, checker scores, token counts, and execution timings.
- **Execution Timings**:
  - `agent_seconds`: Subprocess runtime of the LLM agent.
  - `sandbox_overhead_seconds`: Time consumed creating and destroying the Docker sandbox container.
  - `checker_seconds`: Runtime of `kathara-lab-checker`.
  - `total_seconds`: Total run duration from workspace allocation to run completion.
- **Token Metrics Coherence**:
  - Token counts are extracted from the final `turn.completed` usage event.
  - `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`.
  - `output_tokens`, `reasoning_output_tokens` (reasoning tokens are a subset of output tokens, not double-counted).
  - `total_reported`: Token total reported directly by the provider API.
  - `total_calculated`: `input_tokens + output_tokens`.
  - `total`: Resolves to `total_reported` if available, otherwise `total_calculated`.
- **LLM sampling telemetry** is stored in `logs/aut/sampling_telemetry.json`, `evaluation/metrics.json`, Inspect metadata and aggregate reports. It does not affect scores, token counts or timing.

### LLM sampling telemetry: configuration and evidence

```yaml
aut:
  sampling_telemetry:
    enabled: true
    mode: passive  # passive | http_trace
```

Omitting this section, or setting `enabled: false`, disables collection. A disabled run records `disabled` and does not read sampling logs or add diagnostic settings. Older configurations remain valid.

`passive` uses the existing provider, endpoint, authentication and transport. It inspects only response SSE from the recognizable Codex response trace, if already available; it does not enable tracing. Ordinary JSONL events, arbitrary JSON, prompt text, agent and tool output are not evidence of a server response. `http_trace` is opt-in for the host CLI: it enables trace logging and configures the `chatgpt-http` provider and HTTP transport. This changes experimental conditions relative to the standard path; compare or combine such runs only with that difference explicitly accounted for. Trace logs can contain sensitive content and should be protected.

Docker Sandbox keeps its normal OAuth proxy and execution path in `passive`; `http_trace` is recorded as `unsupported_backend` and does not alter the sandbox. [Docker's credential documentation](https://docs.docker.com/ai/sandboxes/configuration/credentials/) describes proxy-managed authentication, not a supported non-invasive interface for retrieving sampling response metadata. No real-backend availability is established by the simulated tests. If the normal logs do not expose verifiable response traces, the values stay `null`.

The client-requested values, values declared by the server in a response, and values actually applied inside the sampler are distinct. This collector only records values declared in recognizable response traces; those declarations do not prove the internal sampling procedure. It never infers values from model, reasoning effort, or assumed defaults. Numeric finite values are required: temperature must be nonnegative, top_p must be in [0, 1]; provider-specific limits must be checked separately against the actual provider and model. Zero is a number, while `null` means no usable value (CSV/Excel show an empty cell).

`temperature_status` and `top_p_status` are independent: `observed`, `not_reported`, `explicit_null`, `invalid`, `inconsistent`, `unavailable`, `disabled`, or `unsupported_backend`. The overall status is `observed` only when both are observed, `partial` when their states differ, or otherwise reflects the common state or an error. Distinct valid values and response count are retained; disagreements yield a null scalar and `inconsistent`. Historical runs retain their original fields and can be aggregated without invented statuses.

For scientific use, inspect the raw `stderr.log` trace and response IDs alongside the telemetry artifact, check each parameter's status, range and consistency across responses, identify the backend and transport, and retain the experimental configuration. A simulated event or a configured trace mode alone does not establish acquisition, nor does a server declaration establish the actual internal setting. Missing IDs prevent reliable deduplication. Re-aggregate with `python scripts/aggregate_results.py` without rerunning agents.

## Aggregation and Reporting

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

The aggregator processes all `evaluation/metrics.json` files and checker reports in `runs/`. It produces:
- `results/runs.csv`: One row per run detailing identifiers, configuration, status, pass rate, timings, token counts, and correction digests.
- `results/checks.csv`: One row per individual checker test assertion.
- `results/summary.csv`: Aggregated statistics grouped by experiment, scenario, prompt type, skill mode, and model.
- `results/benchmark.xlsx`: Formatted Excel workbook containing `Runs`, `Checks`, and `Summary` sheets with grouped rows, filters, and custom column styling.

## Smoke Check

```bash
python scripts/smoke_check.py
```

The smoke test runs statically without invoking LLM models or launching containers:
1. Validates dependencies and imports (`inspect_ai`, `inspect_swe`, `kathara_lab_checker`, `pandas`, `yaml`, `openai`).
2. Discovers all scenarios and loads configurations.
3. Tests agent dispatch for `codex` and `antigravity`.
4. Statically tests `docker_sandbox_runner` (unique sandbox naming, UUID structure, event parsing, exception hierarchies).
5. Validates cross-provider CLI rejection (e.g. `--agent antigravity` with `benchmark.yaml`).
6. Executes `inspect log dump --header-only` on a generated evaluation sample.
7. Simulates isolated workspace provisioning, diffing, and aggregation.

## Supported Agents

| Agent | CLI / Tool | Config File | Verified Model | Authentication / Execution Backend |
|---|---|---|---|---|
| Codex | `codex` / `sbx` | `benchmark.yaml` | `gpt-5.6-terra` | Local ChatGPT login (Host CLI) / Docker Sandbox (`sbx` OAuth proxy) |
| Antigravity | `agy` | `benchmark_antigravity.yaml` | `gemini-3.8-flash` | Local Google login (Host CLI) |

Both agents operate on the same principle: the agent configures lab files inside an isolated workspace, and Kathara Lab Checker deterministically evaluates the canonical correction on the resulting lab without LLM involvement in evaluation.

## Experiment Layer

The experiment layer orchestrates full matrix runs defined in YAML configuration files without replacing single-scenario commands.

### Key Concepts

| Concept | Description |
|---|---|
| **scenario** | A Kathara lab directory containing baseline `lab/` and `correction.yaml` |
| **prompt_type** | Prompt variation selector (T1–T6) mapping to `prompt/<scenario>/<T>.md` |
| **skill_mode** | Skill condition: `no_skill`, `creation_only`, `dns_only`, `both_forced`, or `auto` |
| **replicate** | Planned statistical repetition index |
| **run_number** | Sequential directory counter (`rNNN`) |
| **experiment** | Matrix definition of `scenario × prompt × skill_mode × replicates` |

`replicate` and `run_number` match under normal execution. If a run fails due to an infrastructure issue and is retried, the retried run receives a new physical `run_number` while fulfilling the original `replicate`.

### Experiment YAML Specification

Create an experiment file under `experiments/` (e.g., `experiments/thesis_final.yaml`):

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

### Running an Experiment

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml
```

The orchestrator pre-validates all scenarios, prompts, skills, corrections, and infrastructure prerequisites before executing any model calls.

### Resuming Interrupted Experiments

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --resume
```

When `--resume` is specified, the orchestrator:
1. Inspects existing runs matching `experiment_id`.
2. Identifies replicates marked with `pipeline_state: COMPLETED` and skips them.
3. Dispatches only missing replicates or runs that failed due to infrastructure errors (`AUT_FAILED`, `CHECKER_FAILED`).
4. Replicates where the agent completed execution but failed lab tests (`task_success: false`) are valid experimental observations and are not retried.

### Rerunning Corrections Across Experiments

To re-evaluate existing runs against updated canonical corrections without making model calls or consuming tokens:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction
```

Filter re-evaluation to specific subsets:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --rerun-correction \
  --filter-scenario lab00_five_router --filter-prompt T1 --filter-skill-mode dns_only
```

Each re-evaluation increments `evaluation_revision` and updates `last_reevaluated_at` in the run manifest.

### Dry Run

Preview the planned run matrix and resume status without executing tasks:

```bash
python scripts/run_experiment.py experiments/thesis_final.yaml --resume --dry-run
```
