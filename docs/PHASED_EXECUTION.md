# Phased experiment execution (opt-in preview)

This document describes the opt-in phased executor. It supports up to 10
concurrent Codex generation workers, 6 Small checkers, 6 Medium checkers and
2 Large checkers. These higher settings have **not** yet been validated against
live Codex OAuth, sbx v0.48.0 and concurrent Kathara Docker workloads on the
target Mac. Verify live isolation and equivalence before relying on new
scientific observations at higher concurrency.

## Design

`scripts/run_experiment.py --pipeline-mode phased` orchestrates two stages:

1. Generate *all* pending AUT observations with up to ten isolated, supervised
   Codex processes. No checker starts during this phase. Each worker writes
   its own manifest, input/output lab, skill-gate evidence, AUT telemetry and
   correction snapshot before returning `AUT_COMPLETED`.
2. Check all eligible labs in order **Small, Medium, Large** with maximum
   worker counts **6, 6, 2**. Only the temporary checker copies receive
   unique Kathara `LAB_NAME` values. The generated lab and correction remain
   unchanged. Each run writes metrics, status and CSV results as soon as its
   checker finishes. Aggregate CSV/Excel files are refreshed after every
   checker wave to avoid reading unfinished reports.

Existing sequential behavior remains the default. Phased execution uses
independent spawned processes (not threads wrapping fork-based supervision).
Each generation has a per-observation lock; the launcher keeps the
experiment lock for the entire execution. The global auth/preflight lock is
kept in place.

## Resource defaults

```yaml
parallel_execution:
  enabled: false
  generation:
    workers: 2
    sandbox_memory: "3g"
    sandbox_cpus: 2
  checker:
    small_workers: 2
    medium_workers: 2
    large_workers: 1
```

`sbx create` supports `--memory` and `--cpus`. These limits are applied
only when phased generation is explicitly selected, including the protected
Skill-gate sandbox. Verify the installed sbx binary's `create --help`.
The defaults above remain unchanged unless overridden. The configured 3g
per-sandbox limit across ten concurrent sandboxes allows up to 30 GB of
sandbox memory consumption, before other Docker/host overhead. These limits
are *ceilings*, not guaranteed free RAM. Monitor swap and memory pressure on
a 16 GB Mac, and lower worker counts if required.

## Ten-generator / six-checker configuration

```bash
.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml \
  --task-level small --replicate 5 --pipeline-mode phased \
  --sandbox-workers 10 --checker-workers 6 --dry-run
```

The limits are shared by YAML validation, the CLI, the executor and the probe.
They do not change the two-worker defaults. At least ten pending generations
are needed to use ten generator slots; filtering to one prompt and five skill
modes permits only five simultaneous generations. A loop over individual prompt
types also runs them in separate batches. Select all pending Small prompts in
one invocation to fill the larger pools. The 10/6 settings require their own
live resource-capacity validation; the successful live 5/4 probe below does not
establish that the 16 GB host can sustain 10/6 for full Small/Medium labs.

## Five-generator / four-checker configuration

Run the offline tests and inspect the planned work before a live experiment:

```bash
.venv/bin/python -m pytest tests/test_phased_execution.py -q

for level in small medium; do
  .venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml \
    --task-level "$level" --repetitions 4 --only-replicate 4 \
    --pipeline-mode phased --generation-workers 5 \
    --checker-workers-small 4 --checker-workers-medium 4 \
    --checker-workers-large 2 --resume --dry-run
done
```

Remove `--dry-run` and prefix the Python command with `caffeinate -i`
only after checking isolation, memory headroom and smoke-test results.
Small and Medium run in sequence in this shell loop. Existing observations
are reused under `--resume` when the fingerprint and artifacts validate.
Note that a statistical replicate (4) is not necessarily a physical directory
named `r004`.

## Offline verification (no LLM calls)

```bash
.venv/bin/python -m pytest tests/test_phased_execution.py -q

.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml \
  --pipeline-mode phased \
  --repetitions 3 --only-replicate 3 --resume \
  --generation-workers 2 \
  --checker-workers-small 2 \
  --checker-workers-medium 2 \
  --checker-workers-large 1 \
  --dry-run
```

The preview must show `GENERATE`, `CHECK`, `SKIP` or `CONFLICT` for the
requested logical observations.

## Live execution (after equivalence validation)

```bash
caffeinate -i .venv/bin/python -u scripts/run_experiment.py \
  experiments/thesis_final.yaml --pipeline-mode phased \
  --repetitions 3 --only-replicate 3 --resume \
  --generation-workers 2 \
  --checker-workers-small 2 \
  --checker-workers-medium 2 \
  --checker-workers-large 1
```

Use the *same command with `--resume`* to continue after an interruption;
it must not regenerate validated `AUT_COMPLETED` workspaces. Do not
concurrently launch the old runner for this experiment.

## Verification required before production use

- Validate that two simultaneous Codex sandboxes (including enforced Skill
  recovery) preserve prompts, gate guarantees, telemetry and cleanup.
- Run small isolated Kathara comparisons with two checkers and compare
  *every* per-test result with the sequential baseline.
- Test crash/resume and stale sandbox/Kathara cleanup in a disposable fixture.
- Test the full CSV/Excel reporting path and file-size-dependent behavior.
- Compare run fingerprints, serialized metrics and token accounting with the
  sequential implementation.
- Run the repository's full offline unit-test suite.

No live sandbox/LLM/checker run was performed during this branch's creation.

## Measured concurrency probe

`scripts/verify_parallel_workers.py` exercises the production phased scheduler
with actual spawned processes and barriers, rather than an inline mock pool:

```bash
.venv/bin/python -B scripts/verify_parallel_workers.py \
  --sandbox-workers 5 --checker-workers 4
```

Add `--live` for five real Codex sandbox environments and the production Kathara
checker on five tiny, independent labs. Add `--model-turn` instead for five short
real model turns as well. Each model turn runs only `sleep 5` and returns its own
marker. These probes save their fixtures, command logs, process samples and
`report.json` in a separate `reports/parallel_worker_probe/<id>/` directory.
Only containers belonging to the probe are removed.

The live infrastructure probe on 2026-11-14 measured five simultaneous sandboxes
and four simultaneous checker OS processes. All five tiny labs passed all four
checks, with no timeout. The probe verifies distinct workspace markers, confirms
that other sandbox workspaces are inaccessible, and checks that generation ends
before checking begins. The first run exposed a missing `default_image` in the
probe fixture; that fixture was corrected before the successful verification.
This is a concurrency/isolation probe, not an equivalence or resource-capacity
test of the full scientific Small/Medium workload or the enforced Skill gate.

The subsequent `--model-turn` probe also succeeded: five overlapping real
`gpt-6.1-terra` Codex invocations, each with one native `turn.completed`, followed
by four simultaneously observed Kathara checker processes. All 20 checks passed
across the five fixtures. Evidence is in the local probe directory
`20261114_175221_ab92e20a`, including native JSON events in `logs/model_turn.json`.
