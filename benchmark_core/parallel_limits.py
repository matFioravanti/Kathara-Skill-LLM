"""Shared worker limits for configuration, CLI, execution and test probes."""

GENERATION_MAX_WORKERS = 10
CHECKER_MAX_WORKERS = {"small": 6, "medium": 6, "large": 2}
