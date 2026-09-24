# Kathara Skill LLM Benchmark

Reproducible benchmark for evaluating CLI LLM agents that configure DNS and web services in Kathara labs. The supported agents are **Codex CLI** and **Antigravity CLI (agy)**, each using strictly local authentication.

## Architecture

Each scenario contains a prompt, a manual correction, and an immutable initial lab. For each skill mode, the runner allocates a fresh run at `runs/<scenario>/<skill_mode>/rNNN`, preserves the baseline in `input/lab`, creates the editable copy in `lab`, and launches the Agent Under Test (AUT) on the host Mac. Run numbers increase independently for each scenario and mode.

The **active agent** of a run is unique: the same agent is used both as the AUT and as the Correction Generator. It is not possible to combine different agents within the same run.

After the AUT finishes, the runner saves its events, closes the measurement window, and computes the diff against the original lab. The Kathara Lab Checker evaluates that run's lab against the manual canonical correction at `scenarios/<scenario>/correction.yaml`. A byte-for-byte snapshot is stored at `evaluation/correction.yaml` for reproducibility. The correction stays outside `lab/` and is not provided to the AUT.

The final result is derived exclusively from the checker. A successful AUT execution can therefore have `aut_execution_success=true`, `checker_execution_success=true`, and `task_success=false`. If the correction or the checker fails because of an infrastructure issue, `task_success` remains null.

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
scenarios/<scenario>/correction.yaml
      │
      ▼
evaluation/correction.yaml → Kathara Lab Checker
      │
      └── checker results

run_id.eval ───────┐
                   ├── aggregation ──► runs.csv / checks.csv / summary.csv
checker results ───┘
```

### Codex Backend

`codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` runs Codex without an API key, passes the prompt via stdin, and preserves all JSONL events.

### Antigravity Backend

`agy --add-dir <workspace> --dangerously-skip-permissions --output-format stream-json --model <model> --effort <effort> --print <prompt>` runs Antigravity with local Google authentication.

### Inspect AI Telemetry

At the end of the AUT, a dedicated adapter reads `result.json` and `events.jsonl` and builds a native Inspect AI log file (`runs/<scenario>/<skill_mode>/rNNN/logs/aut/<scenario>__<skill_mode>__rNNN.eval`). The log records input/output tokens, reasoning tokens, `input_tokens_cache_read`, duration, tool calls, errors, and run metadata. The file can be inspected with `inspect log dump` or `read_eval_log`.

Inspect AI operates exclusively as a telemetry system: it does not wrap the AUT CLI, does not read, generate, or influence `correction.yaml`, and does not participate in lab evaluation. Kathara Lab Checker determines whether checks pass in a fully deterministic manner. The two systems remain separate and are associated only during aggregation through the unique `run_id` identifier.

## Requirements and Installation

Python 3.11 or later, Docker with the daemon running, and Kathara are required. In addition, depending on the selected agent:

* **Codex**: Codex CLI installed and authenticated with ChatGPT (`codex --version`, `codex login status`).
* **Antigravity**: Antigravity CLI installed with local Google authentication (`agy --version`).

It is not necessary to have both installed: the preflight checks only the prerequisites of the configured agent.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` is the freeze of the resolved environment. The core versions are Inspect AI 0.3.266, Inspect SWE 0.2.71, kathara-lab-checker 0.1.14, Kathara 3.8.3, pandas 3.0.6, and PyYAML 6.0.3.

Do not set `OPENAI_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY`, or `INSPECT_EVAL_MODEL`: the runner removes them only from the environment copy passed to the subprocess, without modifying the user's environment.

## Configuration

Each agent has its own dedicated configuration file:

* `benchmark.yaml` — **Codex** configuration (`gpt-5.6-terra`, reasoning effort `low`)
* `benchmark_antigravity.yaml` — **Antigravity** configuration (`gemini-3.8-flash`, reasoning effort `low`)

The agent is determined by the `aut.agent` field in the configuration file. The `--agent` flag on the CLI is used exclusively as a consistency check: it must match `aut.agent` in the YAML, otherwise the command is rejected. Cross-provider override is not supported.

Each scenario has one manual checker correction at `scenarios/<scenario>/correction.yaml`. It is shared by every agent, Skill mode, and repetition for that scenario. The preflight checks that it exists and is valid before any model run; it is not copied into `lab/` and is not provided to the AUT. The checker receives the run's `lab/` and the correction snapshot explicitly. `--rerun-correction` uses the current scenario correction and replaces each selected run's evaluation snapshot.

## Required Skills

The repository prepares the directories but does not invent the Skill or correction content, which must be provided by the experiment:

```text
skills/kathara-creation/SKILL.md
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
scenarios/<scenario>/correction.yaml
```

The Creation Skill must declare `name: kathara-creation`, and the DNS Skill `name: kathara-dns`; both need `description` frontmatter. The Creation Skill content is supplied by the experiment. The checker schema and Skill can be used while authoring corrections, but the benchmark does not run an agent to generate them. To verify the DNS Skill:

```bash
python scripts/run_benchmark.py --check-skills
```

Missing runtime Skills or a scenario correction produce an explicit error before any model call.

Codex experiments select one Skill mode with `--skill-mode`:

| Mode | Available to Codex | Explicitly required |
|------|--------------------|---------------------|
| `no_skill` | none | none |
| `creation_only` | Creation | Creation |
| `dns_only` | DNS | DNS |
| `both_forced` | Creation and DNS | both |
| `auto` | Creation and DNS | none |

The default is `dns_only`, preserving the previous Codex run behavior. Each run receives only the selected skills under `lab/.codex/skills/`. User or parent-scope copies with the same names stop the preflight to prevent contaminated runs. Modes that include Creation require its canonical file at `skills/kathara-creation/SKILL.md`.

`--skill-mode all` is a sequential orchestrator for the five modes above. It validates every required skill before starting, then creates one independent run per mode in the listed order. Each run saves its actual mode in its manifest.

Reevaluate existing runs in place with the updated canonical correction, without model calls or new LLM tokens:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --skill-mode all --rerun-correction
```

With `--all`, every existing scenario is reevaluated. A specific `--skill-mode` limits reevaluation to that mode; omitting it selects all five. All existing `rNNN` directories are processed in order. `--repetitions` is not accepted in this mode.

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --agent codex --skill-mode auto
```

## Scenarios

Scenarios are discovered automatically under `scenarios/` and are valid when they contain:

```text
scenarios/<scenario_id>/
├── prompt.txt
├── correction.yaml
└── lab/
    └── lab.conf
```

Each scenario must contain `prompt.txt`, `correction.yaml`, and `lab/lab.conf`. The correction is manual and shared across agents, Skill modes, and repetitions. Keep it at the scenario root, outside `lab/`; it is never included in the AUT workspace. The prompt is normative, and the lab is copied for each run.

## Execution

Make sure you have activated the virtual environment before running any command:

```bash
source .venv/bin/activate
```

The preflight checks skills, dependencies of the configured agent, Docker, Compose, Kathara, and the checker without making model calls. It checks only the agent specified in the configuration file:

```bash
# Codex preflight (does not require agy)
python scripts/run_benchmark.py --preflight --agent codex

# Antigravity preflight (does not require codex)
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --preflight --agent antigravity
```

Run a scenario:

```bash
# With Codex
python scripts/run_benchmark.py --scenario example_dns_001 --agent codex

# With Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --scenario example_dns_001 --agent antigravity
```

Run five repetitions of all scenarios:

```bash
# With Codex
python scripts/run_benchmark.py --all --repetitions 5 --agent codex

# With Antigravity
python scripts/run_benchmark.py --config benchmark_antigravity.yaml --all --repetitions 5 --agent antigravity
```

`benchmark.continue_on_error` determines whether to continue after an infrastructure-level failed run. An AUT solution evaluated and rejected by the checker is a completed run, not a command error.

## Artifacts and States

Each run uses a readable logical ID, for example `example_dns_001__dns_only__r001`, and preserves:

```text
runs/<scenario>/<skill_mode>/rNNN/
├── manifest.json
├── input/
│   ├── lab/          # original immutable baseline
│   └── prompt.md
├── lab/              # only editable copy — before → after AUT
├── evaluation/
│   ├── correction.yaml  # snapshot of the canonical evaluation input
│   └── metrics.json     # normalized processed metrics for this run
├── results/          # checker CSV reports
└── logs/
    ├── aut/          # events.jsonl, stderr.log, result.json, invocation.json, prompt.txt, <scenario>__<skill_mode>__rNNN.eval
    ├── diff.json
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

`manifest.json` records identifiers, timestamps, versions, skill hashes, status, and artifact references. It records the canonical correction source, its SHA-256 digest, and the snapshot path used by the checker.

`runs/` is the persistent source. Each run stores processed values in `evaluation/metrics.json` beside the original agent trace and checker reports. `results/` contains exactly three derived CSVs:

* `runs.csv` — one row per run, with skill selection, status, timing, tokens, checker counts, and correction digest.
* `checks.csv` — one row per individual Kathara Lab Checker test.
* `summary.csv` — descriptive statistics grouped by scenario and Skill mode.

Token counts come from the last Codex `turn.completed` event carrying a `usage` object in `logs/aut/events.jsonl`. The runner's current trace exposes `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, and `reasoning_output_tokens`; `total_tokens` is kept null when absent. Earlier turn usage events are not added together. `selected_skills` records only available Skill names whose `SKILL.md` is named by a traced `command_execution` read command; it is independent of forced skills.

`agent_seconds` comes from the AUT runner's measured subprocess duration. `checker_seconds` measures `run_checker` including preparation and report parsing. `total_seconds` measures elapsed time from immediately before workspace allocation through completion of the run stages, excluding preflight and the final metrics serialization. In `summary.csv`, `skill_selection_rate` is populated only for `auto`: completed AUTs with a readable trace form the denominator, and runs selecting at least one available Skill form the numerator.

## Aggregation and Analysis

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

The aggregator reads only runs with the `scenario/skill_mode/rNNN/evaluation/metrics.json` layout and saved checker reports. It does not invoke Codex, Docker, Kathara, or the checker, and can be rerun safely with `python scripts/aggregate_results.py`. It writes `runs.csv`, `checks.csv`, and `summary.csv`, plus `benchmark.xlsx` with `Runs`, `Checks`, and `Summary` sheets. The workbook groups rows by scenario with separator lines, formatted headers, filters, and adjusted column widths; other files in `results/` are preserved.

## Smoke Check

```bash
python scripts/smoke_check.py
```

The smoke check statically validates both agents (`codex` and `antigravity`), verifies their AUT dispatch, tests rejection of cross-provider override (`--agent antigravity` with `benchmark.yaml` and vice versa), and simulates aggregation and diff without interacting with the LLMs.

## Supported Agents

| Agent | CLI | Config file | Verified model | Auth |
|-------|-----|-------------|-------------------|------|
| Codex | `codex` | `benchmark.yaml` | `gpt-5.6-terra` | Local ChatGPT login |
| Antigravity | `agy` | `benchmark_antigravity.yaml` | `gemini-3.8-flash` | Local Google login |

Both agents share the same architecture: the agent modifies the lab files invoked from the command line, generates the correction, and Kathara Lab Checker determines the final result without any LLM involvement in the evaluation.
