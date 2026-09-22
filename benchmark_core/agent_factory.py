"""Identità del solo AUT supportato dal backend Codex CLI locale."""

AGENTS = {"codex": "codex_cli", "antigravity": "antigravity_cli"}


def validate_agent(name: str) -> None:
    if name not in AGENTS:
        raise ValueError(f"Questo benchmark supporta esclusivamente gli agenti: {', '.join(AGENTS.keys())}.")
