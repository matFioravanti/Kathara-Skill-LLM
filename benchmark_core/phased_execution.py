"""Two-phase experiment orchestrator (AUT first, then isolated Kathara checks).

This module is opt-in; the historical sequential runner is untouched.
All workers use separate spawned processes. The experiment-level lock is owned
by the launcher. Individual generation runs are supervised independently.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
import json
import sys

from .fingerprint import conditions
from .standard_runtime import validate_artifacts


def _manifest(run: Path) -> dict:
    with (run / "manifest.json").open(encoding="utf-8") as stream:
        return json.load(stream)


def _generate(config, scenario, agent, cell):
    """Executed in a fresh spawned process, not a thread that forks."""
    from .standard_runtime import run_supervised
    from dataclasses import replace
    # Enable resource bounds only for phased AUT; source config stays unchanged.
    parallel = {**config.data.get("parallel_execution", {}), "enabled": True}
    config = replace(config, data={**config.data, "parallel_execution": parallel})
    run = run_supervised(
        config, scenario, agent, cell.prompt_type,
        skill_mode=cell.skill_mode, experiment_id=cell.experiment_id,
        replicate=cell.replicate, assignment=cell.assignment,
        generation_only=True,
    )
    metadata = _manifest(run)
    return str(run), metadata["pipeline_state"]


def _evaluate(config, run_name: str):
    """Evaluate an AUT checkpoint in its own process and Kathara temp lab."""
    from .pipeline import reevaluate_run
    run = Path(run_name)
    metadata = _manifest(run)
    initial = (metadata.get("pipeline_state") == "AUT_COMPLETED"
               and metadata.get("evaluation_revision", 0) == 0)
    reevaluate_run(config, run, isolated_checker=True, initial_evaluation=initial)
    return str(run), _manifest(run)["pipeline_state"]


def execute_phased(config, spec, labs, agent, selected, recoverable, *,
                   generation_workers: int, checker_workers: dict,
                   update_reports, continue_on_error: bool = True):
    """Generate selected observations; only then run checker for each level.

    Existing AUT checkpoints are reused, never regenerated. Persist raw run
    results on every worker completion. Aggregation is done by the parent after
    each wave, with no checker still writing when the aggregation begins.
    """
    if agent != "codex":
        raise ValueError("Parallel phased mode currently requires Codex")
    if config.data.get("docker_sandbox", {}).get("execution_backend") != "docker_sandbox":
        raise ValueError("Parallel phased mode requires Docker Sandboxes")
    if generation_workers not in (1, 2):
        raise ValueError("generation_workers must be 1 or 2 on this host")
    for level in ("small", "medium", "large"):
        count = checker_workers[level]
        if type(count) is not int or count not in (1, 2):
            raise ValueError(f"checker_workers[{level}] must be 1 or 2")
    mp = get_context("spawn")
    generated = {}
    failures = []
    queued = []
    for decision in selected:
        c = decision.cell
        prior = recoverable.get(c)
        if prior is None:
            queued.append(c)
            continue
        expected = conditions(config, labs[c.lab_id], c.prompt_type,
                              c.skill_mode, c.assignment, agent=agent)
        try:
            m = validate_artifacts(prior, expected, completed=False)
            if m.get("aut_execution_success") is not True:
                raise ValueError("AUT was not completed")
            generated[c] = prior
            print(f"[AUT-RESUME] {prior.relative_to(config.root)}", flush=True)
        except Exception as exc:
            # Do not silently duplicate a run with an unverified AUT.
            failures.append((c, str(exc)))
            print(f"[AUT-CONFLICT] {prior}: {exc}", file=sys.stderr, flush=True)

    if failures:
        print("Existing AUT artifacts failed integrity verification; no new generations started.",
              file=sys.stderr, flush=True)
        return True

    print(f"[PHASE 1] {len(queued)} new generations, {len(generated)} recovered; "
          f"{generation_workers} Codex workers", flush=True)
    with ProcessPoolExecutor(max_workers=generation_workers, mp_context=mp) as pool:
        futures = {pool.submit(_generate, config, labs[c.lab_id], agent, c): c
                   for c in queued}
        for future in as_completed(futures):
            cell = futures[future]
            label = (f"{cell.lab_id}/{cell.dns_tree_id}/{cell.task_level}/"
                     f"{cell.prompt_type}/{cell.skill_mode}/rep={cell.replicate}")
            try:
                path, state = future.result()
                run = Path(path)
                if state == "AUT_COMPLETED":
                    generated[cell] = run
                    print(f"[AUT OK] {label}: {run.relative_to(config.root)}", flush=True)
                else:
                    failures.append((cell, state))
                    print(f"[AUT FAILED] {label}: {state}", file=sys.stderr, flush=True)
            except Exception as exc:
                failures.append((cell, f"{type(exc).__name__}: {exc}"))
                print(f"[AUT ERROR] {label}: {exc}", file=sys.stderr, flush=True)
                if not continue_on_error:
                    for pending in futures:
                        pending.cancel()
            # Raw generation metadata is committed by each worker. The parent
            # is the sole writer of aggregate reports.
    update_reports()
    print(f"[PHASE 1 DONE] {len(generated)} available labs, {len(failures)} failures",
          flush=True)

    if failures and not continue_on_error:
        return True

    # Incomplete generations are excluded from checker scheduling.
    checked = 0
    for level in ("small", "medium", "large"):
        candidates = [(cell, path) for cell, path in generated.items()
                      if cell.task_level == level]
        print(f"[PHASE 2] {level}: {len(candidates)} checks, "
              f"{checker_workers[level]} workers", flush=True)
        if not candidates:
            continue
        workers = checker_workers[level]
        # Use waves to keep Excel/CSV aggregation isolated from worker writes.
        for offset in range(0, len(candidates), workers):
            wave = candidates[offset:offset + workers]
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp) as pool:
                pending = {pool.submit(_evaluate, config, str(path)): cell
                           for cell, path in wave}
                for future in as_completed(pending):
                    cell = pending[future]
                    try:
                        path, state = future.result()
                        if state != "COMPLETED":
                            failures.append((cell, state))
                        checked += 1
                        print(f"[CHECK {level}] {checked}: {path} = {state}", flush=True)
                    except Exception as exc:
                        failures.append((cell, f"{type(exc).__name__}: {exc}"))
                        print(f"[CHECK ERROR] {cell}: {exc}",
                              file=sys.stderr, flush=True)
            # Each individual run has already saved metrics and reports. Avoid
            # reading a partly written checker report while its peer is active.
            update_reports()
            if failures and not continue_on_error:
                return True
    print(f"[PHASED DONE] checks={checked}, failures={len(failures)}", flush=True)
    return bool(failures)
