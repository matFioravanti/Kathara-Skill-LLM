"""Caricamento, validazione e snapshot delle correction manuali."""
from pathlib import Path
import hashlib

import yaml


class MissingCorrectionError(ValueError):
    pass


class InvalidCorrectionError(ValueError):
    pass


def correction_path(root: Path, scenario_id: str) -> Path:
    """Percorso canonico sotto scenarios/<id>; nessun fallback legacy."""
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
    if (path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink()
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
