"""Configurazione unica e verifica esplicita delle risorse esterne."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    root: Path
    data: dict

    def path(self, value: str) -> Path:
        return (self.root / value).resolve()

    def model(self, section: str = "aut") -> str | None:
        """Modello facoltativo: null mantiene il default dell'account locale."""
        return self.data[section].get("model") or self.data["aut"].get("model")

    def reasoning_effort(self, section: str = "aut") -> str | None:
        return self.data[section].get("reasoning_effort") or self.data["aut"].get("reasoning_effort")


def load_config(path: Path) -> Config:
    path = path.resolve()
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("benchmark.yaml deve essere una mapping YAML.")
    for section in ("benchmark", "aut", "sandbox", "checker", "results"):
        if not isinstance(data.get(section), dict):
            raise ValueError(f"Sezione mancante/non valida: {section}")
    for key in ("repetitions", "timeout_seconds"):
        value = data["benchmark"].get(key)
        if type(value) is not int or value < 1:
            raise ValueError(f"benchmark.{key} deve essere un intero positivo.")
    for section, key in (("benchmark", "continue_on_error"), ("checker", "no_cache")):
        if type(data[section].get(key)) is not bool:
            raise ValueError(f"{section}.{key} deve essere booleano.")
    if data["checker"].get("report_type") != "csv":
        raise ValueError("Questa integrazione richiede checker.report_type: csv.")
    for section, keys in {
        "aut": ("agent", "version", "dns_skill"),
        "sandbox": ("image",), "results": ("directory",),
    }.items():
        for key in keys:
            if not isinstance(data[section].get(key), str) or not data[section][key].strip():
                raise ValueError(f"{section}.{key} deve essere una stringa non vuota.")
    for section in ("aut",):
        for key in ("model", "reasoning_effort"):
            value = data[section].get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{section}.{key} deve essere null o una stringa non vuota.")
    config = Config(path.parent, data)
    output = config.path(data["results"]["directory"])
    # Impedisce che gli aggregati sovrascrivano dati grezzi o scenari.
    for protected in (config.root, config.root / "runs", config.root / "scenarios", config.root / "skills"):
        if output == protected or (protected != config.root and output.is_relative_to(protected)):
            raise ValueError("results.directory deve essere separata da root, runs, scenarios e skills.")
    return config


def skill_paths(config: Config) -> dict[str, Path]:
    return {"dns": config.path(config.data["aut"]["dns_skill"])}


def verify_skills(config: Config) -> dict[str, Path]:
    paths = skill_paths(config)
    missing = [str(p) for p in paths.values() if not p.is_file() or not p.read_text().strip()]
    if missing:
        raise ValueError("Skill/schema mancanti o vuoti (contenuto non generato):\n" + "\n".join(missing))
    # Il parser ufficiale verifica frontmatter e risorse della skill.
    from .skill_loader import load_skill
    load_skill(paths["dns"])
    return paths
