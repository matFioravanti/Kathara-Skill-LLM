"""Supporto opzionale per scenarios/<scenario>/metadata.yaml.

Il file è completamente opzionale: la sua assenza non influenza né il
benchmark né il Kathara Lab Checker. Serve esclusivamente per classificazione
e analisi dei risultati aggregati.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_scenario_metadata(scenario_dir: Path) -> dict:
    """
    Legge scenarios/<scenario>/metadata.yaml se presente.
    Restituisce un dizionario vuoto se il file non esiste o non è parsabile.
    NON lancia eccezioni: il file è opzionale.
    """
    path = scenario_dir / "metadata.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def scenario_metadata_flat(scenario_dir: Path) -> dict:
    """
    Restituisce i principali metadati in forma piatta per l'integrazione
    nei dataset aggregati. Tutti i campi sono opzionali e None se assenti.
    """
    raw = load_scenario_metadata(scenario_dir)
    topology = raw.get("topology") or {}
    network = raw.get("network") or {}
    services = raw.get("services") or {}
    return {
        "scenario_family": raw.get("family"),
        "topology_routers": topology.get("routers"),
        "topology_hosts": topology.get("hosts"),
        "network_ip_version": network.get("ip_version"),
        "network_routing": network.get("routing"),
        "service_dns": services.get("dns"),
        "service_web": services.get("web"),
        "difficulty": raw.get("difficulty"),
    }
