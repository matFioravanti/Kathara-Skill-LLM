"""Aggregazione deterministica dei soli artefatti già presenti nelle run."""
from pathlib import Path
from datetime import datetime
import os
import json
import re
import statistics
import hashlib
import zipfile
import shutil
import tempfile
import uuid

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from .checker_runner import category as checker_category
from .checker_runner import checker_test_rows, parse_reports
from .check_classification import classify_rows, PRIMARY, SUBCATEGORIES
from .skill_gate import FIELDS as SKILL_GATE_FIELDS
from .report_paths import is_cost266_manifest

RECOVERY_MEAN_FIELDS = (
    'skill_gate_initial_read_seconds', 'skill_gate_retry_seconds', 'skill_gate_fallback_seconds',
    'skill_gate_initial_input_tokens', 'skill_gate_initial_output_tokens',
    'skill_gate_retry_input_tokens', 'skill_gate_retry_output_tokens',
    'skill_gate_fallback_input_tokens', 'skill_gate_fallback_output_tokens',
    'skill_gate_read_attempts', 'skill_gate_retry_count')

RUN_COLUMNS = [
    # 1. IDENTIFICAZIONE
    "ID", "run_directory", "observation_selection", "Lab", "T", "lab_id", "dns_tree_id", "task_level", "prompt_type",
    "experiment_id", "replicate", "run_number", "skill_mode", "skill_protocol",
    "agent", "model", "reasoning_effort", "experimental_fingerprint", "conditions_status",
    "llm_temperature", "llm_top_p",
    "sampling_source", "sampling_status", "sampling_transport", "sampling_collection_mode",
    "sampling_temperature_status", "sampling_top_p_status", "sampling_distinct_temperatures", "sampling_distinct_top_p",

    # 2. METRICHE
    "status", "pipeline_completed", "checker_executed", "task_success",
    "checks_passed", "checks_failed", "checks_total", "pass_rate", "check_pass_rate",
    "report_coverage", "classified_checks",
    "agent_seconds", "checker_seconds", "total_seconds", "cost",
    "prompt_sha256", "prompt_sent_sha256", "correction_sha256",
    "evaluation_revision", "last_reevaluated_at",

    # 3. SKILL
    "available_skills", "forced_skills",

    "internet_used", "internet_status", "web_search_calls", "web_search_attempts",
    "shell_network_candidates", "shell_network_local", "shell_network_uncertain",
    "search_result_domains", "visited_domains", "network_policy", "internet_trace_available",
    "required_skills", "observed_read_skills", "required_reads_observed", "skill_compliance_status",
    "required_skill_count", "required_read_attempt_count", "required_content_identified_count",
    "required_complete_read_count", "required_unverified_read_count",
    "required_reads_complete_before_modification", "protocol_compliance_observed", "skill_strict_status",
    "skill_autonomous_read_before_write", "skill_delivery_before_write", "skill_delivery_details",
    *SKILL_GATE_FIELDS,

    # 4. TOKEN
    "input_tokens", "cached_input_tokens", "output_tokens",
    "reasoning_tokens", "total_tokens",
]
CHECK_COLUMNS = [
    "ID", "Lab", "T", "lab_id", "dns_tree_id", "task_level", "prompt_type", "experiment_id", "skill_mode", "repetition", "replicate",
    "agent", "model",
    "category", "primary_category", "subcategory", "record_type", "classification_source", "test_description", "passed", "reason",
]
SUMMARY_COLUMNS = [
    "experiment_id", "Lab", "T", "lab_id", "dns_tree_id", "task_level", "prompt_type", "skill_mode", "skill_protocol", "agent", "model", "reasoning_effort", "experimental_fingerprint", "conditions_status",
    "skill_gate_recovery_policy_version", "skill_gate_delivery_denominator",
    "skill_gate_direct_runs", "skill_gate_direct_rate",
    "skill_gate_retry_runs", "skill_gate_retry_rate", "skill_gate_fallback_runs", "skill_gate_fallback_rate",
    "skill_conformity_eligible_runs", "skill_autonomous_read_verified_runs",
    "skill_autonomous_read_denominator", "skill_autonomous_read_rate",
    "skill_delivery_verified_runs", "skill_delivery_denominator", "skill_delivery_rate",
    "skill_fallback_verified_runs", "skill_fallback_denominator", "skill_fallback_rate",
    "skill_conformity_unknown_runs", "skill_conformity_unknown_rate",
    "skill_technical_error_runs", "skill_technical_error_rate",
    "skill_gate_error_runs", "agent_post_gate_error_runs", "checker_error_runs",
    "correction_error_runs", "skill_unclassified_error_runs", "skill_delivery_by_skill",
    *(f'mean_{field}' for field in RECOVERY_MEAN_FIELDS),
    "internet_confirmed_runs", "internet_confirmed_denominator", "internet_confirmed_rate",
    "internet_observed_rate",
    "mean_web_search_calls", "web_search_calls_denominator", "internet_unknown_runs",
    "skill_required_runs", "skill_verified_runs", "skill_unobserved_or_unknown_runs",
    "skill_compliance_denominator", "skill_compliance_rate",
    "required_skill_count", "required_read_attempt_count", "required_content_identified_count",
    "required_complete_read_count", "required_unverified_read_count",
    "complete_before_modification_runs", "strict_verified_runs", "strict_compliance_denominator", "strict_observed_compliance_rate",
    "skill_gate_enabled_runs", "skill_gate_blocked_runs", "skill_gate_unsupported_runs",
    "skill_gate_passed_runs", "skill_gate_statuses", "skill_gate_required_skills", "skill_gate_verified_skills",
    "skill_gate_backend_enforcements", "skill_gate_write_attempts_blocked",
    "mean_skill_gate_read_seconds", "mean_skill_gate_verification_seconds",
    "mean_skill_gate_input_tokens", "mean_skill_gate_output_tokens",
    "skill_gate_pass_denominator", "skill_gate_pass_rate", "skill_gate_isolation_violations",
    "mean_skill_gate_write_seconds", "mean_skill_gate_total_seconds",
    "mean_write_phase_input_tokens", "mean_write_phase_output_tokens",
    "total_runs", "physical_attempts", "logical_observations", "pipeline_completed_runs", "checker_executed_runs", "evaluated_runs",
    "sampling_observed_runs", "sampling_temperatures", "sampling_top_ps",
    "task_success_runs", "task_failed_runs", "task_success_rate",
    "mean_checks_passed", "mean_checks_total", "mean_pass_rate", "median_pass_rate", "stdev_pass_rate",
    "mean_agent_seconds", "median_agent_seconds", "stdev_agent_seconds",
    "mean_checker_seconds", "median_checker_seconds",
    "mean_total_seconds", "median_total_seconds", "stdev_total_seconds",
    "mean_input_tokens", "stdev_input_tokens", "mean_cached_input_tokens", "stdev_cached_input_tokens",
    "mean_output_tokens", "stdev_output_tokens",
    "mean_reasoning_tokens", "stdev_reasoning_tokens",
    "mean_total_tokens", "median_total_tokens", "stdev_total_tokens",
]

# Fixed columns keep CSV/workbook schemas stable across data sets.
METRIC_GROUPS = (*PRIMARY, *SUBCATEGORIES, 'dns_record_a', 'dns_record_aaaa',
                 'dns_record_mx', 'dns_record_ns', 'dns_record_unknown')
RUN_COLUMNS += [f'{group}_{field}' for group in METRIC_GROUPS
                for field in ('total', 'passed', 'failed', 'pass_rate')]
SUMMARY_COLUMNS += ['pass_rate_denominator', 'complete_report_runs', 'partial_report_runs',
                    'regular_mean_pass_rate', 'regular_stdev_pass_rate', 'regular_pass_rate_denominator']
SUMMARY_COLUMNS += [f'{prefix}_{group}_{field}' for group in METRIC_GROUPS
                    for field in ('total', 'pass_rate') for prefix in ('mean', 'stdev', 'denominator')]

SKILL_MODE_ORDER = {name: index for index, name in enumerate(
    ("no_skill", "creation_only", "dns_only", "both_forced", "auto")
)}

SKILL_MODE_COLORS = {
    "no_skill": "F2F2F2",      # Grigio chiaro
    "creation_only": "DDEBF7", # Azzurro chiaro
    "dns_only": "FCE4D6",      # Arancione chiaro
    "both_forced": "E2EFDA",   # Verde chiaro
    "auto": "E4DFEC",          # Lilla/viola chiaro
}
PROMPT_ORDER = {f"T{index}": index for index in range(1, 7)}

# Fogli extra rimossi come richiesto. Vengono mantenuti solo Runs, Checks e Summary.


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"JSON non leggibile o non valido: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Il documento deve essere un oggetto JSON: {path}")
    return value


def _natural_key(value):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", str(value or "")))


def _sort_key(row: dict):
    try:
        repetition = int(row.get("repetition"))
    except (TypeError, ValueError):
        repetition = -1
    prompt = str(row.get("prompt_type") or "")
    return (
        _natural_key(row.get("experiment_id")), _natural_key(row.get("Lab")),
        PROMPT_ORDER.get(prompt, 99), prompt,
        SKILL_MODE_ORDER.get(row.get("skill_mode"), 99), str(row.get("skill_mode") or ""),
        str(row.get("skill_protocol") or ""),
        str(row.get("agent") or ""), str(row.get("model") or ""),
        str(row.get("reasoning_effort") or ""), repetition, str(row.get("ID") or ""),
    )


def _check_category(description: str) -> str:
    text = description.casefold()
    if "named is " in text:
        return "dns_authority"
    if any(service in text for service in ("bgpd is ", "ospfd is ", "ospf6d is ",
                                           "ripd is ", "zebra is ", "watchfrr is ")):
        return "routing"
    if "delegat" in text:
        return "dns_delegation"
    known = checker_category(description)
    if known == "dns_authority":
        return "dns_authority"
    if known == "local_ns":
        return "dns_resolution"
    if known == "dns_record":
        return "dns_record"
    if known == "http":
        return "http"
    if known == "reachability" or "reachable from device" in text:
        return "reachability"
    if known == "custom":
        if "route" in text or "routing" in text:
            return "routing"
        if "ip address" in text or "inet" in text or " addr " in f" {text} ":
            return "addressing"
        return "custom"
    if "resolv" in text or "name server" in text or "nameserver" in text:
        return "dns_resolution"
    if "dns" in text and any(word in text for word in ("record", "a record", "aaaa", "mx", "cname")):
        return "dns_record"
    if "dns" in text and any(word in text for word in ("authority", "authoritative")):
        return "dns_authority"
    if "dns" in text and "delegat" in text:
        return "dns_delegation"
    if any(word in text for word in ("checking the routing table", "route show", "routing table", "route ")):
        return "routing"
    if "reachable from device" in text or "ping" in text:
        return "reachability"
    if "ip address" in text or "inet6" in text or "interface" in text and "address" in text:
        return "addressing"
    if "check existence" in text or "collision domain" in text or "lab structure" in text:
        return "topology"
    if text.startswith(("http check", "http check on")):
        return "http"
    return "other"


def _mean(values):
    usable = [number for value in values if (number := _number(value)) is not None]
    return statistics.fmean(usable) if usable else None


def _median(values):
    usable = [number for value in values if (number := _number(value)) is not None]
    return statistics.median(usable) if usable else None


def _stdev(values):
    usable = [number for value in values if (number := _number(value)) is not None]
    return statistics.stdev(usable) if len(usable) > 1 else None


def _run_record(metrics: dict, manifest: dict) -> dict:
    timing = metrics.get("timing") or {}
    tokens = metrics.get("tokens") or {}
    checker = metrics.get("checker") or {}
    tests_passed = _number(checker.get("passed"))
    tests_total = _number(checker.get("total"))
    pass_rate = _number(checker.get("pass_rate"))
    if pass_rate is None and tests_passed is not None and tests_total:
        pass_rate = tests_passed / tests_total
    execution_flag = manifest.get("checker_execution_success")
    status = metrics.get("status") or manifest.get("pipeline_state")
    if "checker_execution_success" in manifest:
        checker_executed = execution_flag is not None
    else:
        checker_executed = (_number(timing.get("checker_seconds")) is not None or status == "COMPLETED")
    evaluated = (manifest.get("pipeline_state", status) == "COMPLETED" and status == "COMPLETED"
                 and (execution_flag is True or "checker_execution_success" not in manifest)
                 and tests_total is not None)
    task_success = manifest.get("task_success")
    if task_success not in (True, False):
        failed_checks = _number(checker.get("failed"))
        task_success = (failed_checks == 0 if failed_checks is not None else tests_passed == tests_total) \
            if evaluated and tests_passed is not None else None

    # experiment_id: può essere None per run storiche senza questo campo
    experiment_id = metrics.get("experiment_id") or manifest.get("experiment_id")
    # replicate: retrocompatibile — se assente usa repetition/run_number
    replicate = (metrics.get("replicate") if isinstance(metrics.get("replicate"), int)
                 else manifest.get("replicate") if isinstance(manifest.get("replicate"), int)
                 else None)
    repetition = metrics.get("run_number", manifest.get("run_number"))
    if replicate is None:
        replicate = repetition  # retrocompatibilità

    def _skill_list_str(value) -> str | None:
        """Serializes a skill list to a semicolon-separated string, or None if unavailable/empty."""
        if isinstance(value, list):
            joined = ";".join(value)
            return joined if joined else None
        return None


    avail_raw = metrics.get("available_skills")
    if not isinstance(avail_raw, list):
        avail_raw = manifest.get("available_skills")
    forced_raw = metrics.get("forced_skills")
    if not isinstance(forced_raw, list):
        forced_raw = manifest.get("forced_skills")

    internet = metrics.get("internet") or {}
    compliance = metrics.get("skill_compliance") or {}
    from .fingerprint import fingerprint, missing_conditions
    recorded_conditions = manifest.get('experimental_conditions')
    recorded_fingerprint = manifest.get('experimental_fingerprint')
    consistent_fields = ('agent', 'model', 'reasoning_effort', 'skill_mode', 'prompt_sha256',
                         'correction_sha256', 'source_lab_sha256')
    consistent = isinstance(recorded_conditions, dict) and all(
        manifest.get(key) == recorded_conditions.get(key) for key in consistent_fields if key in manifest)
    if consistent and recorded_fingerprint == fingerprint(recorded_conditions):
        conditions_status = 'fingerprint_unverified' if missing_conditions(recorded_conditions) else 'verified_fingerprint'
        grouping_fingerprint = recorded_fingerprint
    else:
        fields = ('agent', 'agent_version', 'model', 'reasoning_effort', 'skill_protocol',
                  'prompt_sha256', 'correction_sha256', 'source_lab_sha256',
                  'dns_skill_sha256', 'dns_skill_bundle_sha256', 'creation_skill_sha256',
                  'creation_skill_bundle_sha256', 'timeout_seconds', 'sandbox_image', 'execution_backend')
        known = {field: manifest.get(field) for field in fields}
        grouping_fingerprint = 'legacy-' + fingerprint(known)
        conditions_status = 'invalid_fingerprint' if recorded_fingerprint or recorded_conditions else 'legacy_unverified'
    llm_sampling = metrics.get("llm_sampling") or manifest.get("llm_sampling") or {}
    temperature = _number(llm_sampling.get("temperature"))
    top_p = _number(llm_sampling.get("top_p"))
    sampling_source = llm_sampling.get("source")
    sampling_status = llm_sampling.get("status")
    sampling_transport = llm_sampling.get("transport")

    return {
        **{field: (_skill_list_str(metrics.get(field)) if field in ("skill_gate_required_skills", "skill_gate_verified_skills", "skill_gate_fallback_skills") else json.dumps(metrics[field], ensure_ascii=False) if isinstance(metrics.get(field), (dict, list)) else metrics.get(field)) for field in SKILL_GATE_FIELDS},
        "experiment_id": experiment_id,
        "lab_id": metrics.get("lab_id") or manifest.get("lab_id") or manifest.get("scenario_id") or metrics.get("scenario"),
        "dns_tree_id": metrics.get("dns_tree_id") or manifest.get("dns_tree_id"),
        "task_level": metrics.get("task_level") or manifest.get("task_level"),
        "prompt_type": metrics.get("prompt_type") or manifest.get("prompt_type"),
        "Lab": metrics.get("scenario") or manifest.get("scenario_id"),
        "T": metrics.get("prompt_type") or manifest.get("prompt_type"),
        "skill_mode": metrics.get("skill_mode") or manifest.get("skill_mode"),
        "skill_protocol": metrics.get("skill_protocol") or manifest.get("skill_protocol"),
        "repetition": repetition,
        "replicate": replicate,
        "agent": metrics.get("agent") or manifest.get("agent"),
        "model": metrics.get("model") or manifest.get("model"),
        "reasoning_effort": metrics.get("reasoning_effort") or manifest.get("reasoning_effort"),
        "experimental_fingerprint": grouping_fingerprint,
        "conditions_status": conditions_status,
        "llm_temperature": temperature,
        "llm_top_p": top_p,
        "sampling_source": sampling_source,
        "sampling_status": sampling_status,
        "sampling_transport": sampling_transport,
        "sampling_collection_mode": llm_sampling.get("collection_mode"),
        "sampling_temperature_status": llm_sampling.get("temperature_status"),
        "sampling_top_p_status": llm_sampling.get("top_p_status"),
        "sampling_distinct_temperatures": json.dumps(llm_sampling["distinct_temperatures"]) if "distinct_temperatures" in llm_sampling else None,
        "sampling_distinct_top_p": json.dumps(llm_sampling["distinct_top_p"]) if "distinct_top_p" in llm_sampling else None,
        "status": status,
        "pipeline_completed": manifest.get("pipeline_state", status) == "COMPLETED",
        "checker_executed": checker_executed,
        "task_success": task_success if isinstance(task_success, bool) else None,
        "checks_passed": tests_passed if evaluated else None,
        "checks_total": tests_total if evaluated else None,
        "pass_rate": pass_rate if evaluated else None,
        "agent_seconds": _number(timing.get("agent_seconds")),
        "checker_seconds": _number(timing.get("checker_seconds")),
        "total_seconds": _number(timing.get("total_seconds")),
        "input_tokens": _number(tokens.get("input")),
        "cached_input_tokens": _number(tokens.get("cached_input")),
        "output_tokens": _number(tokens.get("output")),
        "reasoning_tokens": _number(tokens.get("reasoning")),
        "total_tokens": _number(tokens.get("total")),
        "cost": _first_number(metrics.get("cost"), metrics.get("cost_usd"),
                               manifest.get("cost"), manifest.get("cost_usd")),
        "ID": metrics.get("run_id") or manifest.get("run_id"),
        "run_number": repetition,
        "prompt_sha256": metrics.get("prompt_sha256") or manifest.get("prompt_sha256"),
        "prompt_sent_sha256": metrics.get("prompt_sent_sha256") or manifest.get("prompt_sent_sha256"),
        "correction_sha256": metrics.get("correction_sha256") or manifest.get("correction_sha256"),
        "evaluation_revision": metrics.get("evaluation_revision", manifest.get("evaluation_revision", 0)),
        "last_reevaluated_at": metrics.get("last_reevaluated_at") or manifest.get("last_reevaluated_at"),
        "internet_used": internet.get("internet_used"),
        "internet_status": internet.get("status"),
        "web_search_calls": internet.get("web_search_calls"),
        "web_search_attempts": internet.get("web_search_attempts"),
        "shell_network_candidates": internet.get("shell_network_candidates"),
        "shell_network_local": internet.get("shell_network_local"),
        "shell_network_uncertain": internet.get("shell_network_uncertain"),
        "search_result_domains": _skill_list_str(internet.get("search_result_domains")),
        "visited_domains": _skill_list_str(internet.get("visited_domains")),
        "network_policy": internet.get("network_policy"),
        "internet_trace_available": internet.get("trace_available"),
        "required_skills": _skill_list_str(compliance.get("required_skills")),
        "observed_read_skills": _skill_list_str(compliance.get("observed_read_skills")),
        "required_reads_observed": compliance.get("required_reads_observed"),
        "skill_compliance_status": compliance.get("status"),
        "required_skill_count": compliance.get("required_skill_count"),
        "required_read_attempt_count": compliance.get("required_read_attempt_count"),
        "required_content_identified_count": compliance.get("required_content_identified_count"),
        "required_complete_read_count": compliance.get("required_complete_read_count"),
        "required_unverified_read_count": compliance.get("required_unverified_read_count"),
        "required_reads_complete_before_modification": compliance.get("required_reads_complete_before_modification"),
        "protocol_compliance_observed": compliance.get("protocol_compliance_observed"),
        "skill_strict_status": compliance.get("strict_status"),
        "skill_autonomous_read_before_write": metrics.get("skill_autonomous_read_before_write"),
        "skill_delivery_before_write": metrics.get("skill_delivery_before_write"),
        "skill_delivery_details": json.dumps(metrics['skill_delivery_details'], ensure_ascii=False, sort_keys=True)
                                  if isinstance(metrics.get('skill_delivery_details'), dict) else None,
        "available_skills": _skill_list_str(avail_raw),
        "forced_skills": _skill_list_str(forced_raw),

        "_evaluated": evaluated,
        "_manifest": manifest,
    }



def _first_number(*values):
    return next((number for value in values if (number := _number(value)) is not None), None)


def _check_records(run: Path, record: dict) -> list[dict]:
    try:
        raw_rows = checker_test_rows(run / "results")
    except (OSError, ValueError, UnicodeError):
        raw_rows = []
    # The full report is the sole source. The checker also writes a failed-only report;
    # reading that file as well would duplicate failed checks.
    try:
        parsed, _ = parse_reports(run / "results")
        checker = (record.get('_metrics') or {}).get('checker') or {}
        record['_checker_consistent'] = (isinstance(checker, dict)
            and parsed['checks_total'] == checker.get('total')
            and parsed['checks_passed'] == checker.get('passed')
            and parsed['checks_failed'] == checker.get('failed')
            and parsed['task_success'] == record.get('task_success'))
        complete = (record.get("_evaluated") and parsed["detailed_report_available"]
                    and parsed["checks_total"] == record.get("checks_total")
                    and parsed["checks_passed"] == record.get("checks_passed"))
    except (OSError, ValueError, UnicodeError):
        complete = False
        record['_checker_consistent'] = False
    record["report_coverage"] = "complete" if complete else ("partial" if raw_rows else "missing")
    record["checks_failed"] = (record["checks_total"] - record["checks_passed"]
                               if record.get("checks_total") is not None and record.get("checks_passed") is not None else None)
    record["check_pass_rate"] = record.get("pass_rate")
    version = (record.get("_manifest", {}).get("component_versions") or {}).get("kathara-lab-checker")
    correction = run / "evaluation/correction.yaml"
    correction_bytes = None
    try:
        correction_bytes = correction.read_bytes()
        digest = hashlib.sha256(correction_bytes).hexdigest()
        correction_verified = digest == record.get("_manifest", {}).get("correction_sha256")
    except OSError:
        correction_verified = False
    classifications = classify_rows(raw_rows, correction, version, complete and correction_verified, correction_bytes=correction_bytes)
    rows = []
    for check, (primary, subcategory, record_type, source) in zip(raw_rows, classifications):
        description = check.get("test_description") or ""
        rows.append({
            "experiment_id": record.get("experiment_id"),
            **{field: record.get(field) for field in ("lab_id", "dns_tree_id", "task_level", "prompt_type")},
            "Lab": record.get("Lab"), "T": record.get("T"),
            "skill_mode": record.get("skill_mode"), "repetition": record.get("repetition"),
            "replicate": record.get("replicate"),
            "agent": record.get("agent"), "model": record.get("model"),
            "ID": record.get("ID"), "category": _check_category(description),
            "primary_category": primary, "subcategory": subcategory, "record_type": record_type, "classification_source": source,
            "test_description": description, "passed": check.get("passed"), "reason": check.get("reason"),
        })
    record["classified_checks"] = len(rows)
    # Partial data remain inspectable in Checks but cannot enter scientific aggregates.
    if complete:
        for group in METRIC_GROUPS:
            if group == 'other':
                subset = [r for r in rows if r['primary_category'] not in ('network', 'dns')]
            elif group in PRIMARY:
                subset = [r for r in rows if r['primary_category'] == group]
            elif group.startswith('dns_record_'):
                kind = group.removeprefix('dns_record_').upper()
                subset = [r for r in rows if r['subcategory'] == 'dns_record' and r['record_type'] == kind]
                if kind == 'UNKNOWN':
                    subset = [r for r in rows if r['subcategory'] == 'dns_record' and r['record_type'] == 'unknown']
            else:
                subset = [r for r in rows if r['subcategory'] == group]
            total = len(subset)
            passed = sum(r['passed'] is True for r in subset)
            record.update({f'{group}_total': total, f'{group}_passed': passed,
                           f'{group}_failed': total - passed,
                           f'{group}_pass_rate': passed / total if total else None})
    return rows


def _summary_records(records: list[dict]) -> list[dict]:
    groups = {}
    group_fields = ("experiment_id", "Lab", "T", "lab_id", "dns_tree_id", "task_level", "prompt_type", "skill_mode", "skill_protocol", "agent", "model", "reasoning_effort", "experimental_fingerprint", "conditions_status", "skill_gate_recovery_policy_version")
    for record in records:
        key = tuple(record.get(field) for field in group_fields)
        groups.setdefault(key, []).append(record)
    output = []
    for key, group in groups.items():
        evaluated = [row for row in group if row["_evaluated"]]
        task_successes = sum(row.get("task_success") is True for row in evaluated)
        task_failures = sum(row.get("task_success") is False for row in evaluated)
        pass_rates = [row.get("pass_rate") for row in evaluated]
        manifest_states = [row.get("pipeline_completed") for row in group]
        checker_seconds = [row.get("checker_seconds") for row in group]
        observed_sampling = [row for row in group if row.get("sampling_status") in ("observed", "partial")]
        observed_temps = sorted({
            row["llm_temperature"] for row in group if row.get("llm_temperature") is not None
            and (row.get("sampling_temperature_status") == "observed" or
                 (row.get("sampling_temperature_status") is None and row.get("sampling_status") == "observed"))
        })
        observed_top_ps = sorted({
            row["llm_top_p"] for row in group if row.get("llm_top_p") is not None
            and (row.get("sampling_top_p_status") == "observed" or
                 (row.get("sampling_top_p_status") is None and row.get("sampling_status") == "observed"))
        })
        sampling_temps_str = ";".join(str(t) for t in observed_temps) if observed_temps else None
        sampling_top_ps_str = ";".join(str(p) for p in observed_top_ps) if observed_top_ps else None
        stats = {}
        for column, values in (
            ("pass_rate", pass_rates),
            ("agent_seconds", [row.get("agent_seconds") for row in group]),
            ("checker_seconds", checker_seconds),
            ("total_seconds", [row.get("total_seconds") for row in group]),
            ("input_tokens", [row.get("input_tokens") for row in group]),
            ("cached_input_tokens", [row.get("cached_input_tokens") for row in group]),
            ("output_tokens", [row.get("output_tokens") for row in group]),
            ("reasoning_tokens", [row.get("reasoning_tokens") for row in group]),
            ("total_tokens", [row.get("total_tokens") for row in group]),
        ):
            stats[f"mean_{column}"] = _mean(values)
            stats[f"stdev_{column}"] = _stdev(values)
            if column in ("pass_rate", "agent_seconds", "checker_seconds", "total_seconds", "total_tokens"):
                stats[f"median_{column}"] = _median(values)
        
        skill_required = [row for row in group if row.get("required_skills")]
        skill_verified = sum(row.get("required_reads_observed") is True for row in skill_required)
        internet_confirmed = sum(row.get("internet_used") is True for row in group)
        def strict_value(row):
            if row.get('skill_protocol') == 'enforced_read_v1' and row.get('skill_gate_recovery_policy_version') == 'recovery_v1':
                return row.get('skill_autonomous_read_before_write')
            return row.get('protocol_compliance_observed')
        strict_verified = sum(strict_value(row) is True for row in skill_required)
        # Historical protocols retain their original denominator. Recovery has
        # a genuine unknown state that must not be treated as non-compliance.
        strict_denominator = sum(
            1 for row in skill_required
            if not (row.get('skill_protocol') == 'enforced_read_v1' and row.get('skill_gate_recovery_policy_version') == 'recovery_v1')
            or type(strict_value(row)) is bool)
        gate_enabled = sum(row.get("skill_gate_enabled") is True for row in group)
        gate_passed = sum(row.get("skill_gate_status") in ("passed", "write_phase_running", "completed") for row in group)
        delivery = [row for row in group if row.get('skill_gate_enabled') is True
                    and row.get('skill_gate_recovery_policy_version') == 'recovery_v1']
        def delivery_details(row):
            try:
                data = json.loads(row['skill_delivery_details']) if isinstance(row.get('skill_delivery_details'), str) else row.get('skill_delivery_details')
                return data if isinstance(data, dict) else {}
            except ValueError:
                return {}
        def known_boolean(row, field):
            return type(row.get(field)) is bool
        autonomous_known = [row for row in delivery if known_boolean(row, 'skill_autonomous_read_before_write')]
        delivery_known = [row for row in delivery if known_boolean(row, 'skill_delivery_before_write')]
        autonomous_count = sum(row['skill_autonomous_read_before_write'] is True for row in autonomous_known)
        delivery_count = sum(row['skill_delivery_before_write'] is True for row in delivery_known)
        fallback_count = sum(any(d.get('method') == 'preloaded_fallback' and d.get('delivery_before_write') is True
                                 for d in delivery_details(row).values() if isinstance(d, dict)) for row in delivery_known)
        def error_categories(row):
            history = row.get('skill_gate_state_history')
            if isinstance(history, str):
                try: history = json.loads(history)
                except ValueError: history = None
            states = [entry.get('status') for entry in history if isinstance(entry, dict)] if isinstance(history, list) else []
            opened = 'write_phase_running' in states
            failed_aut = row.get('status') == 'AUT_FAILED'
            gate_failed = row.get('skill_gate_status') == 'technical_error'
            gate_error = (gate_failed or failed_aut) and bool(states) and not opened
            # A failure after a completed B may be cleanup or synchronization;
            # its stage is not established by AUT_FAILED alone.
            agent_error = (gate_failed or failed_aut) and opened and 'completed' not in states
            checker_error = row.get('status') == 'CHECKER_FAILED'
            correction_error = row.get('status') in ('CORRECTION_MISSING', 'CORRECTION_INVALID')
            unclassified = (gate_failed or failed_aut) and not gate_error and not agent_error
            return gate_error, agent_error, checker_error, correction_error, unclassified
        category_counts = [sum(error_categories(row)[i] for row in delivery) for i in range(5)]
        # Checker/correction failures exist even for no_skill, auto and older
        # protocols. Count them for the whole group, independently of a gate.
        category_counts[2] = sum(error_categories(row)[2] for row in group)
        category_counts[3] = sum(error_categories(row)[3] for row in group)
        gate_errors = [row for row in delivery if error_categories(row)[0]]
        unknown = [row for row in delivery if not any(error_categories(row))
                   and (not known_boolean(row, 'skill_autonomous_read_before_write')
                        or not known_boolean(row, 'skill_delivery_before_write'))]
        by_skill = {}
        for row in delivery:
            entries = delivery_details(row)
            for skill in (row.get('skill_gate_required_skills') or '').split(';'):
                if not skill:
                    continue
                stats_for_skill = by_skill.setdefault(skill, {'required_runs': 0, 'autonomous_read_verified_runs': 0,
                    'autonomous_read_denominator': 0, 'delivery_verified_runs': 0, 'delivery_denominator': 0,
                    'fallback_verified_runs': 0, 'unknown_runs': 0, 'technical_error_runs': 0,
                    'agent_post_gate_error_runs': 0, 'checker_error_runs': 0,
                    'correction_error_runs': 0, 'unclassified_error_runs': 0})
                detail = entries.get(skill) if isinstance(entries.get(skill), dict) else {}
                a, d = detail.get('autonomous_read_before_write'), detail.get('delivery_before_write')
                stats_for_skill['required_runs'] += 1
                stats_for_skill['autonomous_read_denominator'] += type(a) is bool
                stats_for_skill['autonomous_read_verified_runs'] += a is True
                stats_for_skill['delivery_denominator'] += type(d) is bool
                stats_for_skill['delivery_verified_runs'] += d is True
                stats_for_skill['fallback_verified_runs'] += detail.get('method') == 'preloaded_fallback' and d is True
                errors = error_categories(row)
                if any(errors):
                    for label, flag in zip(('technical_error_runs', 'agent_post_gate_error_runs',
                                            'checker_error_runs', 'correction_error_runs', 'unclassified_error_runs'), errors):
                        stats_for_skill[label] += flag
                elif type(a) is not bool or type(d) is not bool:
                    stats_for_skill['unknown_runs'] += 1
        for value in by_skill.values():
            for label, count, denominator in [('autonomous_read_rate', 'autonomous_read_verified_runs', 'autonomous_read_denominator'),
                                               ('delivery_rate', 'delivery_verified_runs', 'delivery_denominator'),
                                               ('fallback_rate', 'fallback_verified_runs', 'delivery_denominator')]:
                value[label] = value[count] / value[denominator] if value[denominator] else None
        def has_method(row, method):
            value = row.get('skill_gate_load_methods')
            if isinstance(value, str):
                value = json.loads(value)
            return isinstance(value, dict) and method in value.values()
        methods = {}
        for label, method in [('direct', 'read_verified'), ('retry', 'retry_verified'), ('fallback', 'preloaded_fallback')]:
            count = sum(has_method(row, method) for row in delivery)
            methods[f'skill_gate_{label}_runs'] = count
            methods[f'skill_gate_{label}_rate'] = count / len(delivery) if delivery else None
        def known_total(field):
            values = [_number(row.get(field)) for row in group]
            values = [v for v in values if v is not None]
            return sum(values) if values else None
        category_stats = {}
        valid = [row for row in evaluated if row.get('report_coverage') == 'complete']
        for metric_group in METRIC_GROUPS:
            for field in ('total', 'pass_rate'):
                values = [row.get(f'{metric_group}_{field}') for row in valid]
                category_stats[f'mean_{metric_group}_{field}'] = _mean(values)
                category_stats[f'stdev_{metric_group}_{field}'] = _stdev(values)
                category_stats[f'denominator_{metric_group}_{field}'] = sum(_number(v) is not None for v in values)
        output.append({
            **category_stats,
            'pass_rate_denominator': sum(_number(v) is not None for v in pass_rates),
            'complete_report_runs': len(valid),
            'regular_mean_pass_rate': _mean(row.get('pass_rate') for row in valid),
            'regular_stdev_pass_rate': _stdev(row.get('pass_rate') for row in valid),
            'regular_pass_rate_denominator': sum(_number(row.get('pass_rate')) is not None for row in valid),
            'partial_report_runs': sum(row.get('report_coverage') == 'partial' for row in group),
            **dict(zip(group_fields, key)),
            **methods,
            'skill_conformity_eligible_runs': len(delivery),
            'skill_autonomous_read_verified_runs': autonomous_count,
            'skill_autonomous_read_denominator': len(autonomous_known),
            'skill_autonomous_read_rate': autonomous_count / len(autonomous_known) if autonomous_known else None,
            'skill_delivery_verified_runs': delivery_count,
            'skill_delivery_denominator': len(delivery_known),
            'skill_delivery_rate': delivery_count / len(delivery_known) if delivery_known else None,
            'skill_fallback_verified_runs': fallback_count,
            'skill_fallback_denominator': len(delivery_known),
            'skill_fallback_rate': fallback_count / len(delivery_known) if delivery_known else None,
            'skill_conformity_unknown_runs': len(unknown),
            'skill_conformity_unknown_rate': len(unknown) / len(delivery) if delivery else None,
            'skill_technical_error_runs': len(gate_errors),
            'skill_technical_error_rate': len(gate_errors) / len(delivery) if delivery else None,
            **dict(zip(('skill_gate_error_runs', 'agent_post_gate_error_runs', 'checker_error_runs',
                        'correction_error_runs', 'skill_unclassified_error_runs'), category_counts)),
            'skill_delivery_by_skill': json.dumps(by_skill, ensure_ascii=False, sort_keys=True) if by_skill else None,
            **{f'mean_{field}': _mean(row.get(field) for row in group) for field in RECOVERY_MEAN_FIELDS},
            'skill_gate_delivery_denominator': len(delivery),
            "internet_confirmed_runs": internet_confirmed,
            "internet_confirmed_denominator": len(group),
            "internet_confirmed_rate": internet_confirmed / len(group),
            "internet_observed_rate": internet_confirmed / len(group),
            "internet_unknown_runs": sum(row.get("internet_used") is None for row in group),
            "mean_web_search_calls": _mean(row.get("web_search_calls") for row in group),
            "web_search_calls_denominator": sum(_number(row.get("web_search_calls")) is not None for row in group),
            "skill_required_runs": len(skill_required),
            "skill_verified_runs": skill_verified,
            "skill_unobserved_or_unknown_runs": len(skill_required) - skill_verified,
            "skill_compliance_denominator": len(skill_required),
            "skill_compliance_rate": skill_verified / len(skill_required) if skill_required else None,
            **{field: known_total(field) for field in ("required_skill_count", "required_read_attempt_count", "required_content_identified_count", "required_complete_read_count", "required_unverified_read_count")},
            "complete_before_modification_runs": sum(row.get("required_reads_complete_before_modification") is True for row in skill_required),
            "skill_gate_enabled_runs": sum(row.get("skill_gate_enabled") is True for row in group),
            "skill_gate_blocked_runs": sum(row.get("skill_gate_blocked") is True for row in group),
            "skill_gate_unsupported_runs": sum(row.get("skill_gate_status") == "unsupported_backend" for row in group),
            "skill_gate_passed_runs": gate_passed,
            "skill_gate_pass_denominator": gate_enabled,
            "skill_gate_pass_rate": gate_passed / gate_enabled if gate_enabled else None,
            "skill_gate_isolation_violations": known_total("skill_gate_isolation_violations"),
            "skill_gate_statuses": ";".join(sorted({row["skill_gate_status"] for row in group if row.get("skill_gate_status")})) or None,
            "skill_gate_required_skills": ";".join(sorted({skill for row in group for skill in (row.get("skill_gate_required_skills") or "").split(";") if skill})) or None,
            "skill_gate_verified_skills": ";".join(sorted({skill for row in group for skill in (row.get("skill_gate_verified_skills") or "").split(";") if skill})) or None,
            "skill_gate_backend_enforcements": ";".join(sorted({row["skill_gate_backend_enforcement"] for row in group if row.get("skill_gate_backend_enforcement")})) or None,
            "skill_gate_write_attempts_blocked": known_total("skill_gate_write_attempts_blocked"),
            "mean_skill_gate_read_seconds": _mean(row.get("skill_gate_read_seconds") for row in group),
            "mean_skill_gate_verification_seconds": _mean(row.get("skill_gate_verification_seconds") for row in group),
            "mean_skill_gate_write_seconds": _mean(row.get("skill_gate_write_seconds") for row in group),
            "mean_skill_gate_total_seconds": _mean(row.get("skill_gate_total_seconds") for row in group),
            "mean_write_phase_input_tokens": _mean(row.get("write_phase_input_tokens") for row in group),
            "mean_write_phase_output_tokens": _mean(row.get("write_phase_output_tokens") for row in group),
            "mean_skill_gate_input_tokens": _mean(row.get("skill_gate_input_tokens") for row in group),
            "mean_skill_gate_output_tokens": _mean(row.get("skill_gate_output_tokens") for row in group),
            "strict_verified_runs": strict_verified,
            "strict_compliance_denominator": strict_denominator,
            "strict_observed_compliance_rate": strict_verified / strict_denominator if strict_denominator else None,
            "total_runs": len(group),
            "logical_observations": len(evaluated),
            "pipeline_completed_runs": sum(state is True for state in manifest_states),
            "checker_executed_runs": sum(row.get("checker_executed") is True for row in group),
            "evaluated_runs": len(evaluated),
            "sampling_observed_runs": len(observed_sampling),
            "sampling_temperatures": sampling_temps_str,
            "sampling_top_ps": sampling_top_ps_str,
            "task_success_runs": task_successes,
            "task_failed_runs": task_failures,
            "task_success_rate": task_successes / len(evaluated) if evaluated else None,
            "mean_checks_passed": _mean(row.get("checks_passed") for row in evaluated),
            "mean_checks_total": _mean(row.get("checks_total") for row in evaluated),
            **stats,
        })

    return sorted(output, key=_sort_key)


# Fogli analitici rimossi (Dashboard, Matrix, Lab Summary, ecc.)



# ---------------------------------------------------------------------------
# Scrittura CSV e Excel
# ---------------------------------------------------------------------------

def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, na_rep="", lineterminator="\n")
    temporary.replace(path)


def _style_sheet(sheet, frame: pd.DataFrame, is_runs_sheet: bool = False) -> None:
    # Colori per i tre blocchi nel foglio Runs
    header_font = Font(color="FFFFFF", bold=True)
    id_fill = PatternFill("solid", fgColor="2F5597")      # Blu scuro
    metrics_fill = PatternFill("solid", fgColor="385723") # Verde scuro
    tokens_fill = PatternFill("solid", fgColor="C55A11")  # Arancione scuro
    default_fill = PatternFill("solid", fgColor="17365D") # Colore di default per altri fogli
    
    body_fill = PatternFill("solid", fgColor="F4F7FA")
    empty_fill = PatternFill(fill_type=None)
    skill_fills = {name: PatternFill("solid", fgColor=color) for name, color in SKILL_MODE_COLORS.items()}
    alignments = {False: Alignment(vertical="top", wrap_text=False), True: Alignment(vertical="top", wrap_text=True)}
    styles = {}
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 90
    sheet.auto_filter.ref = sheet.dimensions
    
    for column_index, column_name in enumerate(frame.columns, start=1):
        cell = sheet.cell(1, column_index)
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        
        if is_runs_sheet:
            col_name_str = str(column_name)
            # Determina il gruppo in base all'indice o nome
            if "token" in col_name_str.lower():
                cell.fill = tokens_fill
            elif col_name_str in (
                "ID", "Lab", "T", "experiment_id", "replicate", "run_number",
                "skill_mode", "skill_protocol", "agent", "model", "reasoning_effort",
                "llm_temperature", "llm_top_p", "sampling_source", "sampling_status", "sampling_transport"
            ):
                cell.fill = id_fill
            else:  # Le colonne in mezzo sono metriche
                cell.fill = metrics_fill
        else:
            cell.fill = default_fill

    sheet.row_dimensions[1].height = 32
    for column_index, column in enumerate(frame.columns, start=1):
        values = [str(column)] + [str(value) for value in frame[column].dropna().head(100)]
        width = min(max(max(map(len, values), default=12) + 2, 12), 52)
        if column in ("ID", "run_id", "prompt_sha256", "correction_sha256"):
            width = 44 if column in ("ID", "run_id") else 38
        elif column in ("reason", "test_description"):
            width = 52
        sheet.column_dimensions[sheet.cell(1, column_index).column_letter].width = width
        is_skill_mode_col = (column == "skill_mode")
        for row_index in range(2, sheet.max_row + 1):
            cell = sheet.cell(row_index, column_index)
            skill = str(cell.value) if is_skill_mode_col and cell.value else None
            if column.endswith("rate") or column == "pass_rate":
                number_format = "0.00%"
            elif column == "cost":
                number_format = "$#,##0.0000"
            elif column in ("llm_temperature", "llm_top_p"):
                number_format = "0.0#"
            elif "seconds" in column:
                number_format = "0.0"
            elif "tokens" in column or column in (
                "repetition", "replicate", "run_number", "checks_passed", "checks_total", "total_runs",
                "pipeline_completed_runs", "checker_executed_runs", "evaluated_runs", "sampling_observed_runs",
                "task_success_runs", "task_failed_runs", "run_count", "scenarios", "prompt_types", "skill_modes",
                "replicates", "infrastructure_failures", "completed_runs"):
                number_format = "#,##0"
            else:
                number_format = None
            key = (cell.style_id, row_index % 2, skill if skill in skill_fills else None,
                   column in ("reason", "test_description"), number_format)
            if key in styles:
                cell._style = styles[key]
                continue
            
            # Gestione sfondo: alternato di default, oppure basato su skill_mode
            if is_skill_mode_col:
                val = str(cell.value) if cell.value else ""
                bg_color = SKILL_MODE_COLORS.get(val)
                if bg_color:
                    cell.fill = skill_fills[val]
                else:
                    cell.fill = body_fill if row_index % 2 == 0 else empty_fill
            else:
                cell.fill = body_fill if row_index % 2 == 0 else empty_fill
                
            cell.alignment = alignments[column in ("reason", "test_description")]
            if column.endswith("rate") or column == "pass_rate":
                cell.number_format = "0.00%"
            elif column == "cost":
                cell.number_format = "$#,##0.0000"
            elif column in ("llm_temperature", "llm_top_p"):
                cell.number_format = "0.0#"
            elif "seconds" in column:
                cell.number_format = "0.0"
            elif "tokens" in column or column in (
                "repetition", "replicate", "run_number",
                "checks_passed", "checks_total", "total_runs",
                "pipeline_completed_runs", "checker_executed_runs", "evaluated_runs",
                "sampling_observed_runs",
                "task_success_runs", "task_failed_runs", "run_count",
                "scenarios", "prompt_types", "skill_modes", "replicates",
                "infrastructure_failures", "completed_runs",
            ):
                cell.number_format = "#,##0"
            styles[key] = cell._style
    for row_index in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row_index].height = 21


def _write_excel(
    path: Path,
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    extra_frames: dict[str, pd.DataFrame] | None = None,
) -> None:
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    all_sheets = list(zip(("Runs", "Checks", "Summary"), frames))
    if extra_frames:
        all_sheets += list(extra_frames.items())
    if sum(frame.size for _, frame in all_sheets) > 250_000:
        # Streaming avoids materializing millions of styled openpyxl cells.
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.utils import get_column_letter

        book = Workbook(write_only=True)
        book.properties.created = book.properties.modified = datetime(2000, 1, 1)
        max_data_rows = 1_048_575  # Excel limit includes the header.
        for name, frame in all_sheets:
            def new_sheet(part):
                sheet = book.create_sheet(name if part == 1 else f'{name}_{part}')
                sheet.freeze_panes = 'A2'
                sheet.auto_filter.ref = f'A1:{get_column_letter(len(frame.columns))}{min(len(frame) - (part - 1) * max_data_rows, max_data_rows) + 1}'
                for index in range(1, len(frame.columns) + 1):
                    sheet.column_dimensions[get_column_letter(index)].width = 20
                header = []
                for column in frame.columns:
                    cell = WriteOnlyCell(sheet, value=str(column))
                    cell.font = Font(bold=True, color='FFFFFF')
                    cell.fill = PatternFill('solid', fgColor='305496')
                    header.append(cell)
                sheet.append(header)
                return sheet
            sheet = new_sheet(1)
            for index, row in enumerate(frame.itertuples(index=False, name=None)):
                if index and index % max_data_rows == 0:
                    sheet = new_sheet(index // max_data_rows + 1)
                sheet.append([None if pd.isna(value) else value for value in row])
        book.save(temporary)
    else:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            writer.book.properties.created = datetime(2000, 1, 1)
            writer.book.properties.modified = datetime(2000, 1, 1)
            for name, frame in all_sheets:
                frame.to_excel(writer, sheet_name=name, index=False, na_rep="")
                _style_sheet(writer.sheets[name], frame, is_runs_sheet=(name == "Runs"))
    canonical = path.with_name(f"{path.stem}.canonical{path.suffix}")
    with zipfile.ZipFile(temporary, "r") as source, zipfile.ZipFile(
        canonical, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as target:
        for name in sorted(source.namelist()):
            original = source.getinfo(name)
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = original.create_system
            info.external_attr = original.external_attr
            info.internal_attr = original.internal_attr
            if name == "docProps/core.xml":
                content = source.read(name)
                content = re.sub(
                    rb"(<dcterms:modified\b[^>]*>).*?(</dcterms:modified>)",
                    rb"\g<1>2000-01-01T00:00:00Z\g<2>", content,
                )
                target.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            else:
                with source.open(name) as src, target.open(info, 'w') as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
    os.replace(canonical, temporary)
    temporary.replace(path)


def aggregate(runs: Path, results: Path, *, experiment_id: str | None = None,
              legacy_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Aggregate, retaining a separate diagnostic without replacing prior reports on failure."""
    runs, results = Path(runs), Path(results)
    if results.resolve().is_relative_to(runs.resolve()):
        raise ValueError(f"La directory report non può trovarsi nelle run: {results}")
    try:
        if experiment_id is not None and legacy_only:
            raise ValueError('Selezionare un esperimento o le run legacy, non entrambi')
        return _aggregate_impl(runs, results, experiment_id=experiment_id, legacy_only=legacy_only)
    except Exception as exc:
        try:
            from .workspace import write_json
            path = results / '.diagnostics' / f'{uuid.uuid4().hex}.json'
            write_json(path, {'error_type': type(exc).__name__, 'message': str(exc), 'runs_root': str(runs)})
        except Exception:
            pass  # Never hide the original aggregation error.
        raise


def _aggregate_impl(runs: Path, results: Path, *, experiment_id: str | None = None,
                    legacy_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Rigenera CSV e workbook dai manifest, metrics e report già salvati."""
    validate_report_destination(results)
    records, check_records, incomplete = [], [], []
    if not runs.is_dir():
        raise ValueError(f"Directory delle run inesistente o non valida: {runs}")
    if runs.exists():
        for base, dirs, _ in os.walk(runs):
            relative = Path(base).relative_to(runs)
            if legacy_only and len(relative.parts) >= 4:
                dirs[:] = []
            if experiment_id is not None and not relative.parts:
                dirs[:] = [name for name in dirs if name == experiment_id]
            if len(relative.parts) in (4, 7) and re.fullmatch(r'r\d{3,}', relative.name):
                manifest_path = Path(base) / 'manifest.json'
                if not manifest_path.is_file():
                    raise ValueError(f"Directory run senza manifest: {manifest_path}")
                dirs[:] = []
    for manifest_path in runs.rglob('manifest.json'):
        parts = manifest_path.relative_to(runs).parts
        if experiment_id is not None and (len(parts) != 8 or parts[0] != experiment_id):
            continue
        if legacy_only and len(parts) != 5:
            continue
        if len(parts) not in (5, 8) or not re.fullmatch(r'r\d{3,}', parts[-2]):
            continue
        manifest = _read_json(manifest_path)
        if is_cost266_manifest(manifest):
            continue
        if experiment_id is not None and manifest.get('experiment_id') != experiment_id:
            raise ValueError(f"Esperimento incoerente nel manifest: {manifest_path}")
        if manifest.get('pipeline_state') == 'COMPLETED' and not (manifest_path.parent / 'evaluation/metrics.json').is_file():
            raise ValueError(f"Run COMPLETED senza metriche: {manifest_path.parent / 'evaluation/metrics.json'}")
        if not (manifest_path.parent / 'evaluation/metrics.json').is_file():
            incomplete.append((manifest_path.parent, manifest))
    for metrics_path in runs.rglob("metrics.json"):
        if metrics_path.parent.name != "evaluation":
            continue
        try:
            parts = metrics_path.relative_to(runs).parts
        except ValueError:
            continue
        if experiment_id is not None and (len(parts) != 9 or parts[0] != experiment_id):
            continue
        if legacy_only and len(parts) != 6:
            continue
        if (len(parts) not in (6, 9) or parts[-2:] != ("evaluation", "metrics.json")
                or not re.fullmatch(r"r\d{3,}", parts[-3])):
            continue
        run = metrics_path.parent.parent
        manifest_path = run / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"Manifest mancante per metriche esistenti: {manifest_path}")
        manifest = _read_json(manifest_path)
        if is_cost266_manifest(manifest):
            continue
        metrics = _read_json(metrics_path)
        for key in ('timing', 'tokens', 'checker', 'internet', 'skill_compliance', 'llm_sampling'):
            if metrics.get(key) is not None and not isinstance(metrics[key], dict):
                raise ValueError(f"Campo {key} non valido in {metrics_path}: atteso oggetto JSON")
        if manifest.get('component_versions') is not None and not isinstance(manifest['component_versions'], dict):
            raise ValueError(f"Campo component_versions non valido in {manifest_path}")
        record = _run_record(metrics, manifest)
        record['_run_path'] = str(run.relative_to(runs))
        record['_metrics'] = metrics
        if record['conditions_status'] == 'invalid_fingerprint':
            raise ValueError(f"Fingerprint non valida: {manifest_path}")
        records.append(record)
        check_records.extend(_check_records(run, record))
        if len(parts) == 9 and manifest.get('pipeline_state') == 'COMPLETED':
            correction = run / 'evaluation/correction.yaml'
            try:
                correction_hash = hashlib.sha256(correction.read_bytes()).hexdigest()
            except OSError:
                correction_hash = None
            if (not record['_checker_consistent'] or metrics.get('status') != 'COMPLETED'
                    or not manifest.get('run_id') or metrics.get('run_id') != manifest['run_id']
                    or type(manifest.get('replicate')) is not int or manifest['replicate'] < 1
                    or metrics.get('replicate') != manifest['replicate']
                    or manifest.get('checker_execution_success') is not True
                    or type(manifest.get('task_success')) is not bool
                    or not manifest.get('correction_sha256') or correction_hash != manifest['correction_sha256']
                    or not (run / 'lab').is_dir() or not (run / 'input/lab').is_dir()):
                raise ValueError(f"Artefatti, report checker o metriche non validi/incoerenti: {run}")
            for key in ('experiment_id', 'lab_id', 'dns_tree_id', 'task_level', 'prompt_type', 'skill_mode'):
                if manifest.get(key) is None or metrics.get(key) != manifest.get(key):
                    raise ValueError(f"Identità {key} mancante o incoerente: {metrics_path}")
            for key in ('agent', 'model', 'reasoning_effort'):
                if key in manifest and metrics.get(key) != manifest[key]:
                    raise ValueError(f"Campo {key} incoerente: {metrics_path}")

    for run, manifest in incomplete:
        record = _run_record({}, manifest)
        record['_run_path'] = str(run.relative_to(runs))
        records.append(record)
        check_records.extend(_check_records(run, record))

    records.sort(key=_sort_key)
    check_records.sort(key=lambda row: (
        _sort_key(row), row.get("category") or "", row.get("test_description") or "",
        bool(row.get("passed")), row.get("reason") or "",
    ))
    check_frame = pd.DataFrame(check_records, columns=CHECK_COLUMNS)
    # A logical observation with multiple completed physical attempts is ambiguous.
    # Preserve every raw row/check, but exclude all completed candidates from statistics.
    identity_fields = ('experiment_id', 'lab_id', 'dns_tree_id', 'task_level', 'prompt_type', 'skill_mode', 'replicate')
    by_identity = {}
    all_attempts = {}
    for record in records:
        identity = tuple(record.get(field) for field in identity_fields)
        if all(value is not None and value != '' for value in identity):
            all_attempts.setdefault(identity, []).append(record)
            if record.get('pipeline_completed'):
                by_identity.setdefault(identity, []).append(record)
    duplicates = []
    excluded = set()
    exclusions = []
    for identity, group in sorted(by_identity.items(), key=lambda item: str(item[0])):
        if len(group) < 2:
            continue
        fingerprints = [r['_manifest'].get('experimental_fingerprint') for r in group]
        known = [f for f in fingerprints if isinstance(f, str)]
        legacy_fields = ('agent', 'model', 'reasoning_effort', 'skill_protocol', 'prompt_sha256',
                         'correction_sha256', 'source_lab_sha256', 'dns_skill_sha256', 'creation_skill_sha256')
        differs = any(len({str(r['_manifest'].get(field)) for r in group if r['_manifest'].get(field) is not None}) > 1
                      for field in legacy_fields)
        condition_status = 'conflitto' if differs or len(set(known)) > 1 else ('verificate' if len(known) == len(group) and all(r['conditions_status'] == 'verified_fingerprint' for r in group) else 'non_verificabili')
        duplicates.append({'identity': dict(zip(identity_fields, identity)), 'conditions': condition_status,
                           'policy': 'exclude_all_completed',
                           'attempts': [{'path': r['_run_path'], 'fingerprint': r['_manifest'].get('experimental_fingerprint')}
                                        for r in group]})
        excluded.update(id(r) for r in group)
    for identity, attempts in all_attempts.items():
        if len(attempts) < 2:
            continue
        completed = by_identity.get(identity, [])
        for record in attempts:
            if record not in completed or len(completed) != 1:
                excluded.add(id(record))
                exclusions.append({'identity': dict(zip(identity_fields, identity)),
                                   'path': record['_run_path'],
                                   'reason': ('ambiguous_completed' if len(completed) > 1 else
                                              'superseded_failed_attempt' if completed else 'multiple_incomplete_attempts')})
    for record in records:
        record['run_directory'] = record['_run_path']
        record['observation_selection'] = 'excluded_duplicate' if id(record) in excluded else (
            'included' if record.get('_evaluated') else 'unevaluated')
    run_frame = pd.DataFrame([{key: record.get(key) for key in RUN_COLUMNS} for record in records],
                             columns=RUN_COLUMNS)
    summary_records = _summary_records([r for r in records if id(r) not in excluded])
    physical_group_fields = ("experiment_id", "Lab", "T", "lab_id", "dns_tree_id", "task_level", "prompt_type", "skill_mode", "skill_protocol", "agent", "model", "reasoning_effort", "experimental_fingerprint", "conditions_status", "skill_gate_recovery_policy_version")
    for summary in summary_records:
        summary['physical_attempts'] = sum(all(record.get(field) == summary.get(field) for field in physical_group_fields)
                                           for record in records)
    summary_frame = pd.DataFrame(summary_records, columns=SUMMARY_COLUMNS)

    _publish_generation(results, run_frame, check_frame, summary_frame,
                        {'policy': 'exclude_all_completed', 'duplicates': duplicates, 'exclusions': exclusions,
                         'physical_attempts': len(records), 'excluded_completed_attempts': sum(id(r) in excluded and r.get('pipeline_completed') for r in records),
                         'excluded_physical_attempts': len(excluded)})
    return run_frame, check_frame, summary_frame


def validate_report_destination(results: Path):
    for path in (results,*results.parents):
        if path.exists() and not path.is_dir():
            raise ValueError(f'Percorso report occupato, preservato: {path}')
    names = ('runs.csv', 'checks.csv', 'summary.csv', 'benchmark.xlsx', 'duplicates.json', 'report_manifest.json')
    for name in names:
        path = results / name
        if (path.exists() or path.is_symlink()) and (not path.is_symlink() or os.readlink(path) != f'current/{name}'):
            raise ValueError(f'Report preesistente non gestito, preservato: {path}; usare una nuova directory --report-output o --output')
    current = results / 'current'
    if current.exists() and not current.is_symlink():
        raise ValueError(f'Percorso current non valido: {current}')


def _publish_generation(results: Path, run_frame, check_frame, summary_frame, duplicate_report):
    """Publish one immutable generation through an atomic current symlink.

    Existing regular legacy reports are never overwritten; choose a new output directory.
    """
    from .workspace import write_json
    names = ('runs.csv', 'checks.csv', 'summary.csv', 'benchmark.xlsx', 'duplicates.json', 'report_manifest.json')
    validate_report_destination(results)
    results.mkdir(parents=True, exist_ok=True)
    current = results / 'current'
    generations = results / '.generations'
    generations.mkdir(exist_ok=True)
    generation_id = uuid.uuid4().hex
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=generations))
    try:
        for name, frame in [('runs.csv', run_frame), ('checks.csv', check_frame), ('summary.csv', summary_frame)]:
            _atomic_csv(staging / name, frame)
        write_json(staging / 'duplicates.json', duplicate_report)
        _write_excel(staging / 'benchmark.xlsx', (run_frame, check_frame, summary_frame))
        with zipfile.ZipFile(staging / 'benchmark.xlsx') as book:
            if book.testzip() is not None or 'xl/workbook.xml' not in book.namelist():
                raise ValueError('Workbook generato non valido')
        for name in ('runs.csv', 'checks.csv', 'summary.csv'):
            if not (staging / name).is_file() or not (staging / name).stat().st_size:
                raise ValueError(f'Report CSV vuoto: {name}')
        digests = {}
        for name in names[:-1]:
            h = hashlib.sha256()
            with (staging / name).open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    h.update(block)
            digests[name] = h.hexdigest()
        write_json(staging / 'report_manifest.json', {'generation_id': generation_id, 'sha256': digests,
                                                      'duplicate_policy': duplicate_report['policy']})
        final = generations / generation_id
        staging.rename(final)
        for name in names:
            path = results / name
            if not path.is_symlink():
                path.symlink_to(f'current/{name}')
        pointer = results / f'.current-{generation_id}'
        pointer.symlink_to(f'.generations/{generation_id}')
        os.replace(pointer, current)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
