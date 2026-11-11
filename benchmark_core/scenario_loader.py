from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    directory: Path

    @property
    def lab(self) -> Path:
        return self.directory / "lab"

    @property
    def correction(self) -> Path:
        return self.directory / "correction.yaml"

def discover_scenarios(directory: Path) -> dict[str, Scenario]:
    scenarios = {}
    if not directory.is_dir():
        raise ValueError(f"Directory scenari non trovata: {directory}")
    for path in sorted(directory.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", path.name):
            raise ValueError(f"Scenario ID non valido: {path.name}")
        if path.is_symlink() or (path / "lab").is_symlink() or (path / "correction.yaml").is_symlink():
            raise ValueError(f"Scenario con directory simboliche non supportato: {path}")
        # Una struttura con sole correction canoniche e segnaposto non è un lab
        # eseguibile finché manca il lab.conf della baseline. Mantenerla senza
        # segnalarla come scenario malformato; altri file reali restano errori.
        if not (path / "lab/lab.conf").is_file() and (path / "lab").is_dir():
            tasks_root = path / "tasks"

            def scaffold_entry(entry: Path) -> bool:
                if entry.is_symlink():
                    return False
                if entry.is_dir():
                    return True
                if not entry.is_file():
                    return False
                if entry.name == ".gitkeep":
                    return True
                return (entry.name in {"correction.yaml", "bindings.yaml"}
                        and tasks_root in entry.parents)

            if all(scaffold_entry(entry) for entry in path.rglob("*")):
                continue
        required_files = [path / "lab/lab.conf"]
        for required in required_files:
            if not required.is_file():
                raise ValueError(f"Scenario incompleto: manca {required}")
        scenario = Scenario(path.name, path.resolve())
        scenarios[path.name] = scenario
    return scenarios
