# Checker-only Kathara capacity test

This command never calls Codex. It selects existing AUT snapshots and uses the
production `run_checker` on independent copies. It does not aggregate or write
`thesis_final` results. Without `--execute`, only selection, hashes, parsing and
Docker inventory are checked. A new report directory is required each time.

```bash
caffeinate -i .venv/bin/python -u scripts/stress_test_kathara.py \
  --experiment thesis_final --task-level small --num-labs 15 --workers 15 --execute
```

Use `--dry-run` instead to inspect the selection without starting containers.
The implementation was delivered with a dry-run only; 15-way live stability
has not been established.

For a progressive comparison, each level uses the same 15 originals:

```bash
caffeinate -i .venv/bin/python -u scripts/stress_test_kathara.py \
  --experiment thesis_final --task-level small --num-labs 15 \
  --levels 1,2,4,6,8,10,12,15 --repetitions 2 \
  --sample-interval 5 --timeout 900 --execute
```

Other options: `--output-dir PATH`, `--memory-fraction 0.85`,
`--max-infra-errors 2`, `--no-start-barrier`.
`--selection-file results/stress_tests/<id>/selection.json` reuses a frozen
selection and rejects originals whose recorded hashes changed. Failed functional
checks remain valid inputs. Incomplete AUTs, active observations, invalid snapshots,
symlinks, host lifecycle hooks and external/bridged dependencies are excluded.

## Isolation and lifecycle

The launcher holds a shared experiment lock; the main benchmark takes an exclusive
lock, so original observations cannot be regenerated or reevaluated concurrently.
The original selected run trees are hashed before and after execution. The original
correction snapshot is copied byte-for-byte, never regenerated from current scenarios.
Only `LAB_NAME` in the stress copy changes. The existing checker then makes its own
temporary copy with that same identity, preserving the label during cleanup.

Kathara's installed parser derives `lab_hash` from `LAB_NAME`; its Docker backend
labels containers and networks with `app=kathara` and `lab_hash`. Stress instances
receive independent random names, their hashes are checked for collisions before
launch, and shared collision domains must be disabled. Fallback cleanup requires
both labels, an exact hash allowlist and exclusion of preexisting resource IDs.
It never calls global prune, wipe, or global cleanup. Normal checker cleanup is
scoped to its own temporary lab. Ctrl+C or guards signal only these checker process
groups, allow scoped cleanup, and then remove any remaining owned resources.
Queued jobs are not launched after an abort. Hard process/host termination cannot
execute Python finally blocks; the saved selection, instance hashes and logs allow
manual, scoped recovery. Existing resources are never considered cleanup targets.

## Measurements and interpretation

- Samples are scheduled every 5 seconds. Actual timestamps and raw data are saved;
  slow Docker or macOS queries may increase the effective interval.
- Checker concurrency is measured from actual OS command lines, separately from
  workers and queue length. Lab concurrency comes from running Docker containers
  carrying each instance's hash. A fully started lab requires all expected devices.
- Container CPU, reported used memory and per-lab sums are recorded. CPU sums can
  exceed 100% across cores. The configured memory limit is never counted as usage.
- Exact total used RAM of the Docker Desktop VM is unavailable through the inspected
  interface and is null. Container sums can include shared accounting and are NOT
  reported as exact VM RAM. The 85% guard uses total container-reported consumption
  divided by Docker Engine `MemTotal`, explicitly a conservative budget proxy.
  It includes other containers for safety; stress-only usage is also recorded.
- macOS host CPU comes from `top`; free pages, swap and raw pressure information
  are retained. Free pages are not presented as available/reclaimable memory.
  Critical pressure is recognized only when `kern.memorystatus_vm_pressure_level`
  supplies the known critical value 4; otherwise this guard is unavailable.
- Confirmed OOM stops the test. Nonzero container exits are recorded with their
  code and stop state, without calling them OOM. Repeated checker infrastructure
  failures stop scheduling. A transient stats timeout leaves its metrics missing;
  inventory failures pause new launches and are retried. Prolonged lost visibility
  leads to a controlled stop. `--docker-timeout`, `--monitor-retries`,
  `--monitor-backoff`, `--monitor-max-errors` and `--monitor-max-blind-seconds`
  tune the policy. Docker stats calls run serially in the monitoring thread.
- Startup is measured from Docker create/start events, when every expected device
  start was observed. Missing events produce null. Checker duration includes the
  existing checker's deployment, convergence, tests and cleanup, not test execution
  alone. The deployment interval and total checker interval are distinct fields.
  `verification_seconds_observed` separately measures the interval between the
  checker's "Starting tests" and "Undeploying Network Scenario" log messages,
  observed at 0.1-second intervals; it is null when either marker is unavailable.
- Per-level throughput counts completed evaluations, including functional FAIL.
  Samples provide lower-bound peaks and sustained durations. Completion alone is
  not evidence that all 15 labs were simultaneously running.

Reports under `results/stress_tests/<id>/` include `summary.json`,
`measurements.csv`, `laboratories.csv`, `docker_events.log`, `stress_test.log`,
`report.md`, `selection.json`, original provenance and per-instance checker logs.
Six PNG charts are generated when matplotlib is installed; unavailable metrics
remain null. Repeated stable levels receive means and standard deviations.
A candidate optimum requires at least two repeated levels that sustained their
configured concurrency for at least ten sampled seconds. The plateau heuristic
marks a measured throughput gain of at most 5%; neither is a universal host limit.

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_kathara_stress.py tests/test_checker_integrity_and_csv.py \
  tests/test_phased_execution.py tests/test_assignment_integration.py \
  tests/test_rerun_correction.py
```

These tests use mocked Docker and checker payloads. They do not start a live lab
or model turn. The only extension to the shared checker is an optional cooperative
cancellation event; the benchmark's default timeout and execution path remain intact.
