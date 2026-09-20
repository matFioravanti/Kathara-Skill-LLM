"""Identità del solo AUT supportato dal backend Codex CLI locale."""

AGENTS = {"codex": "codex_cli"}


def validate_agent(name: str) -> None:
    if name != "codex":
        raise ValueError("Questo benchmark usa esclusivamente la Codex CLI locale autenticata.")
