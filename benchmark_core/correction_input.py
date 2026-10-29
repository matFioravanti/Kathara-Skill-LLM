"""Caricamento, validazione e snapshot delle correction manuali."""
from pathlib import Path
import hashlib

import yaml


class MissingCorrectionError(ValueError):
    pass


class InvalidCorrectionError(ValueError):
    pass


def correction_path(root: Path, scenario_id, dns_tree_id: str | None = None, task_level: str | None = None) -> Path:
    """Percorso canonico sotto scenarios/<id>; nessun fallback legacy."""
    from .task_catalog import TaskAssignment, task_correction_path
    if isinstance(scenario_id, TaskAssignment):
        return task_correction_path(root, scenario_id)
    if dns_tree_id is not None or task_level is not None:
        return task_correction_path(root, TaskAssignment(scenario_id, dns_tree_id, task_level))
    return root / "scenarios" / scenario_id / "correction.yaml"


def _display_path(path: Path) -> str:
    parts = path.parts
    if "scenarios" in parts:
        index = len(parts) - 1 - tuple(reversed(parts)).index("scenarios")
        return Path(*parts[index:]).as_posix()
    return path.as_posix()


def read_correction(path: Path) -> tuple[bytes, str]:
    """Legge una correction una sola volta e valida col parser ufficiale del checker."""
    display = _display_path(path)
    if (any(parent.is_symlink() for parent in (path, *list(path.parents)[:4]))
            or not path.is_file()):
        raise MissingCorrectionError(f"Missing correction file: {display}\nNo model run was started.")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise InvalidCorrectionError(f"Cannot read correction file: {display}: {exc}") from exc
    try:
        data = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InvalidCorrectionError(f"Invalid correction file: {display}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise InvalidCorrectionError(f"Invalid correction file: {display}: expected a non-empty YAML mapping.")
    try:
        # Il loader ufficiale del Kathara Lab Checker valida i campi e lab_inline.
        from kathara_lab_checker.__main__ import load_config_and_lab
        from Kathara.parser.netkit.LabParser import LabParser

        _, structure = load_config_and_lab(str(path))
        try:
            template = LabParser().parse(str(Path(structure).parent), conf_name=Path(structure).name)
            if not template.machines:
                raise ValueError("lab_inline non contiene dispositivi.")
        finally:
            Path(structure).unlink(missing_ok=True)
    except Exception as exc:
        raise InvalidCorrectionError(f"Invalid correction file: {display}: {exc}") from exc
    return content, hashlib.sha256(content).hexdigest()


def validate_correction(path: Path) -> str:
    """Valida la correction al preflight e restituisce il digest del contenuto."""
    return read_correction(path)[1]


def validate_correction_lab(path: Path, lab: Path) -> None:
    """Verify that the checker's template references only baseline machines."""
    from kathara_lab_checker.__main__ import load_config_and_lab
    from Kathara.parser.netkit.LabParser import LabParser

    _, structure = load_config_and_lab(str(path))
    try:
        expected = LabParser().parse(str(Path(structure).parent), conf_name=Path(structure).name)
        baseline = LabParser().parse(str(lab), conf_name="lab.conf")
        missing = set(expected.machines) - set(baseline.machines)
        if missing:
            raise ValueError(f"Dispositivi della correction assenti dal laboratorio: {', '.join(sorted(missing))}")
        for name, machine in expected.machines.items():
            actual = baseline.machines[name].interfaces
            for number, interface in machine.interfaces.items():
                if number not in actual or actual[number].link.name != interface.link.name:
                    raise ValueError(f"Topologia incompatibile per {name}[{number}]")
    finally:
        Path(structure).unlink(missing_ok=True)
