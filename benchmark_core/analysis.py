"""Lettura del summary.csv prodotto dall'aggregatore; non crea output duplicati."""
from pathlib import Path

import pandas as pd


def analyze(results: Path) -> pd.DataFrame:
    return pd.read_csv(results / "summary.csv")
