# Phased experiment execution (opt-in preview)

This document describes the experimental implementation on branch
\`feature/phased-parallel-benchmark\`. This path has **not** yet been validated
against live Codex OAuth, sbx v0.48.0 and concurrent Kathara Docker workloads
on the target Mac. Do not use it to generate scientific observations before
testing its equivalence to the existing sequential protocol.

## Design

\`scripts/run_experiment.py --pipeline-mode phased\` orchestrates two stages:

1. Generate *all* pending AUT observations with up to two isolated, supervised
   Codex processes. No checker starts during this phase. Each worker writes
   its own manifest, input/output lab, skill-gate evidence, AUT telemetry and
   correction snapshot before returning \`AUT_COMPLETED\`.
2. Check all eligible labs in order **Small, Medium, Large** with maximum
   worker counts **2, 2, 1**. Only the temporary checker copies receive
   unique Kathara \`LAB_NAME\` values. The generated lab and correction remain
   unchanged. Each run writes metrics, status and CSV results as soon as its
   checker finishes. Aggregate CSV/Excel files are refreshed after every
   checker wave to avoid reading unfinished reports.

Existing sequential behavior remains the default. Phased execution uses
independent spawned processes (not threads wrapping fork-based supervision).
Each generation has a per-observation lock; the launcher keeps the
experiment lock for the entire execution. The global auth/preflight lock is
kept in place.

## Resource defaults

\`\`\`yaml
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
\`\`\`

\`sbx create\` supports \`--memory\` and \`--cpus\`. These limits are applied
only when phased generation is explicitly selected, including the protected
Skill-gate sandbox. Verify the installed sbx binary's \`create --help\`.
The memory allocations are *limits*, not guaranteed free RAM. If the Mac
uses excessive swap or Codex fails to initialize, use
\`--generation-workers 1\` and reduce memory pressure.

## Offline verification (no LLM calls)

\`\`\`bash
.venv/bin/python -m pytest tests/test_phased_execution.py -q

.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml \
  --pipeline-mode phased \
  --repetitions 3 --only-replicate 3 --resume \
  --generation-workers 2 \
  --checker-workers-small 2 \
  --checker-workers-medium 2 \
  --checker-workers-large 1 \
  --dry-run
\`\`\`

The preview must show \`GENERATE\`, \`CHECK\`, \`SKIP\` or \`CONFLICT\` for the
requested logical observations.

## Live execution (after equivalence validation)

\`\`\`bash
caffeinate -i .venv/bin/python -u scripts/run_experiment.py \
  experiments/thesis_final.yaml --pipeline-mode phased \
  --repetitions 3 --only-replicate 3 --resume \
  --generation-workers 2 \
  --checker-workers-small 2 \
  --checker-workers-medium 2 \
  --checker-workers-large 1
\`\`\`

Use the *same command with \`--resume\`* to continue after an interruption;
it must not regenerate validated \`AUT_COMPLETED\` workspaces. Do not
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
