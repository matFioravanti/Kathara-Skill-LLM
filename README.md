# Kathara Skill LLM Benchmark

Reproducible benchmark for evaluating CLI LLM agents that configure DNS and web services in Kathara labs. The supported agents are **Codex CLI** and **Antigravity CLI (agy)**, each using strictly local authentication.

## Architecture

Each scenario contains only a prompt and an immutable initial lab. For each repetition, the runner preserves the baseline in `runs/<run_id>/input/lab`, creates the editable copy in `runs/<run_id>/lab`, and launches the Agent Under Test (AUT) on the host Mac.

The **active agent** of a run is unique: the same agent is used both as the AUT and as the Correction Generator. It is not possible to combine different agents within the same run.

After the first execution finishes, the runner saves the native JSONL events, closes the measurement window, and computes the diff against the original lab. A second execution of the same agent, with separate logs, reads the protected final lab, the original prompt, the checker skill, and the schema. This call produces `correction.yaml`; its metrics never enter the AUT results.

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
generate_correction()
      │
      ▼
Kathara Lab Checker
      │
      └── checker results

run_id.eval ───────┐
                   ├── aggregation ──► benchmark_results.csv
checker results ───┘
```

### Codex Backend

`codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` runs Codex without an API key, passes the prompt via stdin, and preserves all JSONL events.

### Antigravity Backend

`agy --add-dir <workspace> --dangerously-skip-permissions --output-format stream-json --model <model> --effort <effort> --print <prompt>` runs Antigravity with local Google authentication.

### Inspect AI Telemetry

At the end of the AUT, a dedicated adapter reads `result.json` and `events.jsonl` and builds a native Inspect AI log file (`runs/<run_id>/logs/aut/<run_id>.eval`). The log records input/output tokens, reasoning tokens, `input_tokens_cache_read`, duration, tool calls, errors, and run metadata. The file can be inspected with `inspect log dump` or `read_eval_log`.

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

The Correction Generator always uses the same agent as the AUT. If `correction_generator.agent` is specified in the YAML, it must match `aut.agent`.

## Required Skills

The repository prepares the directories but does not invent the skill content, which must be provided by the experiment:

```text
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
```

The two skills must have frontmatter compatible with the Agent Skills specification (`name` and `description`). The first is visible only to the AUT. The second is visible only to the correction generator; the schema is mounted separately as read-only. To verify presence and validity:

```bash
python scripts/run_benchmark.py --check-skills
```

The absence of any of these files produces an explicit error before any model call.

## Scenarios

Scenarios are discovered automatically under `scenarios/` and are valid when they contain:

```text
scenarios/<scenario_id>/
├── prompt.txt
└── lab/
    └── lab.conf
```

Do not add `scenario.yaml` or `correction.yaml`. The prompt is the normative source; `lab/` is copied for each run and is not modified.

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

Each run uses a readable and unique ID, for example `example_dns_001__antigravity__r001__20260922T151828726332Z_77f85f8d`, and preserves:

```text
runs/<run_id>/
├── manifest.json
├── input/
│   ├── lab/          # original immutable baseline
│   └── prompt.md
├── lab/              # only editable copy — before → after AUT
├── correction.yaml
├── results/          # checker CSV reports
└── logs/
    ├── aut/          # events.jsonl, stderr.log, result.json, invocation.json, prompt.txt, <run_id>.eval
    ├── generator/    # active agent log for the correction generator
    ├── generator_output/  # candidate correction.yaml before validation
    ├── diff.json
    ├── lab_integrity.json
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

`manifest.json` records identifiers, timestamps, versions, skill hashes, status, and artifact references. It includes `execution_backend` (`codex_cli` or `antigravity_cli`), `authentication` (`local_chatgpt_login` or `local_google_login`), `correction_agent`, and `correction_backend`.

`runs/` is the persistent source. `results/` contains derived reports that can be rebuilt at any time:
* `results/benchmark_report.xlsx` — main Excel report with formatted sheets `Runs` (including Inspect telemetry), `Telemetry`, and `Analysis` (bold headers, freeze panes, automatic filters, percentages, and PASS/FAIL conditional formatting)
* `results/benchmark_results.csv` — CSV overview per run
* `results/benchmark_detailed.csv` — CSV detail and textual Reason for every individual check
* `results/analysis_summary.csv` — aggregated statistics

## Aggregation and Analysis

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

The aggregator combines metrics and states, generating both the CSV files and the Excel report `results/benchmark_report.xlsx`. It automatically distinguishes between Codex and Antigravity telemetry formats, converts them into native Inspect AI `.eval` logs, and associates them with Kathara Lab Checker reports through `run_id`.

## Smoke Check

```bash
python scripts/smoke_check.py
```

The smoke check statically validates both agents (`codex` and `antigravity`), verifies dispatch for the AUT and correction generator, tests rejection of cross-provider override (`--agent antigravity` with `benchmark.yaml` and vice versa), and simulates aggregation and diff without interacting with the LLMs.

## Supported Agents

| Agent | CLI | Config file | Verified model | Auth |
|-------|-----|-------------|-------------------|------|
| Codex | `codex` | `benchmark.yaml` | `gpt-5.6-terra` | Local ChatGPT login |
| Antigravity | `agy` | `benchmark_antigravity.yaml` | `gemini-3.8-flash` | Local Google login |

Both agents share the same architecture: the agent modifies the lab files invoked from the command line, generates the correction, and Kathara Lab Checker determines the final result without any LLM involvement in the evaluation.
