"""CLI e parser del formato reale kathara-lab-checker 0.1.14."""
from pathlib import Path
import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile

from .workspace import copy_lab, write_json

CATEGORIES = ("dns_authority", "local_ns", "dns_record", "http", "reachability", "custom")
REPORT_COLUMNS = ["Test Description", "Passed", "Reason"]


def category(description: str) -> str | None:
    # Descrizioni verificate nei sorgenti dei check 0.1.14; nessun ID inventato.
    if description.startswith("Checking on `") and "is the authority for domain" in description:
        return "dns_authority"
    if description.startswith("Checking that `") and "is the local name server for device" in description:
        return "local_ns"
    if description == "Checking correctness of DNS records":
        return "dns_record"
    if description.startswith(("HTTP check '", "HTTP Check on ")):
        return "http"
    if description.startswith("Verifying `") and "reachable from device" in description:
        return "reachability"
    if description.startswith(("Checking the exit code of the command '", "Checking the output of the command '")):
        return "custom"
    return None


def read_csv(path: Path, columns: list[str]) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != columns:
            raise ValueError(f"Formato report inatteso in {path}: {reader.fieldnames}")
        return list(reader)


def parse_reports(reports: Path) -> tuple[dict, list[dict]]:
    global_rows = read_csv(reports / "results.csv", ["Student Name", "Tests Passed", "Tests Failed",
                                                    "Tests Total Number", "Problems"])
    if len(global_rows) != 1 or global_rows[0]["Student Name"] != "lab":
        raise ValueError("Atteso esattamente il laboratorio 'lab' nel report globale.")
    total_row = global_rows[0]
    passed, failed, total = (int(total_row[x]) for x in ("Tests Passed", "Tests Failed", "Tests Total Number"))
    if total < 1 or passed < 0 or failed < 0 or passed + failed != total:
        raise ValueError("Conteggi checker vuoti o incoerenti.")
    all_file = reports / "lab/lab_result_all.csv"
    # Il checker emette solo results.csv quando lab.conf AUT non è parsabile.
    # Non inventare un singolo check dettagliato a partire dal testo Problems.
    if not all_file.exists():
        if not (passed == 0 and failed == total == 1 and
                total_row["Problems"].startswith("1: The lab.conf cannot be parsed:")):
            raise ValueError("Report dettagliato mancante.")
        rows = []
    else:
        rows = read_csv(all_file, REPORT_COLUMNS)
        if len(rows) != total or any(row["Passed"] not in ("True", "False") for row in rows):
            raise ValueError("Report dettagliato incoerente o valori Passed non booleani.")
        if sum(row["Passed"] == "True" for row in rows) != passed:
            raise ValueError("Conteggi globale/dettaglio non corrispondono.")
        summary = read_csv(reports / "lab/lab_result_summary.csv", ["Total Tests", "Passed Tests", "Failed"])
        if len(summary) != 1 or [int(summary[0][k]) for k in ("Total Tests", "Passed Tests", "Failed")] != [total, passed, failed]:
            raise ValueError("Summary incoerente.")
        failures = read_csv(reports / "lab/lab_result_failed.csv", REPORT_COLUMNS)
        if failures != [row for row in rows if row["Passed"] == "False"]:
            raise ValueError("Report failed incoerente.")
    result = dict(checks_passed=passed, checks_failed=failed, checks_total=total,
                  check_pass_rate=passed / total, task_success=failed == 0,
                  checker_problems=total_row["Problems"], detailed_report_available=bool(rows))
    for name in CATEGORIES:
        subset = [r for r in rows if category(r["Test Description"]) == name]
        result[f"{name}_pass_rate"] = (sum(r["Passed"] == "True" for r in subset) / len(subset)
                                       if subset else None)
    return result, rows


def run_checker(config, run: Path) -> dict:
    lab = run / "lab"
    results = run / "results"
    correction = run / "correction.yaml"

    # Il checker scrive CSV dentro la sua labs_path e dentro labs_path/<lab_name>/,
    # quindi serve una directory temporanea per evitare che inquini run/lab/.
    # La tempdir viene rimossa automaticamente al termine.
    # Non collocare la tempdir dentro la run: anche un arresto non intercettabile del
    # processo Python non deve lasciare una terza copia persistente tra gli artefatti.
    with tempfile.TemporaryDirectory(prefix=f"kathara-checker-{run.name}-") as tmp_str:
        tmp = Path(tmp_str)
        tmp_labs = tmp / "labs"
        tmp_labs.mkdir()
        copy_lab(lab, tmp_labs / "lab")
        # Rimuovi eventuali report iniettati dall'AUT nella copia temporanea.
        for name in ("lab_result_all.csv", "lab_result_failed.csv", "lab_result_summary.csv", "lab_result.xlsx"):
            (tmp_labs / "lab" / name).unlink(missing_ok=True)
        command = [sys.executable, "-m", "kathara_lab_checker", "--config", str(correction),
                   "--labs", str(tmp_labs), "--report-type", "csv"]
        if config.data["checker"]["no_cache"]:
            command.append("--no-cache")
        write_json(run / "logs" / "checker_invocation.json", {"command": command})
        code = None
        timed_out = False
        with (run / "logs" / "checker_stdout.log").open("w") as stdout, \
             (run / "logs" / "checker_stderr.log").open("w") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=config.data["benchmark"]["timeout_seconds"])
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                timed_out = True
                # SIGINT richiama la pulizia del laboratorio corrente prevista dal checker.
                os.killpg(process.pid, signal.SIGINT)
                try:
                    code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait()
                if isinstance(exc, KeyboardInterrupt):
                    raise
            finally:
                # Copia i report dalla tempdir a results/ prima che la tempdir venga rimossa.
                for relative in ("results.csv", "lab/lab_result_all.csv",
                                 "lab/lab_result_failed.csv", "lab/lab_result_summary.csv"):
                    source = tmp_labs / relative
                    if source.is_file() and not source.is_symlink():
                        target = results / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                write_json(run / "logs" / "checker_execution.json",
                           {"returncode": code, "timed_out": timed_out})
        # tempdir rimossa automaticamente all'uscita del with

    if timed_out or code != 0:
        raise RuntimeError(f"Checker fallito: returncode={code}, timeout={timed_out}; vedere checker_stderr.log.")
    result, _ = parse_reports(results)
    return result
