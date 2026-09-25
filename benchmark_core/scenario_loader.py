from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    directory: Path
    prompt_file: Path | None = None

    @property
    def lab(self) -> Path:
        return self.directory / "lab"

    @property
    def correction(self) -> Path:
        return self.directory / "correction.yaml"

    @property
    def prompt(self) -> str:
        return (self.prompt_file or (self.directory / "prompt.txt")).read_text(encoding="utf-8")

    def with_prompt(self, prompt_file: Path) -> "Scenario":
        return Scenario(self.scenario_id, self.directory, prompt_file.resolve())


def discover_scenarios(directory: Path) -> dict[str, Scenario]:
    scenarios = {}
    if not directory.is_dir():
        raise ValueError(f"Directory scenari non trovata: {directory}")
    for path in sorted(directory.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", path.name):
            raise ValueError(f"Scenario ID non valido: {path.name}")
        for required in (path / "prompt.txt", path / "correction.yaml", path / "lab/lab.conf"):
            if not required.is_file():
                raise ValueError(f"Scenario incompleto: manca {required}")
        if path.is_symlink() or (path / "lab").is_symlink() or (path / "correction.yaml").is_symlink():
            raise ValueError(f"Scenario con directory simboliche non supportato: {path}")
        scenario = Scenario(path.name, path.resolve())
        if not scenario.prompt.strip():
            raise ValueError(f"Prompt vuoto: {path}")
        scenarios[path.name] = scenario
    return scenarios
