"""Local development QA entry points.

These scripts are intentionally small wrappers so quality commands can be
standardized via [project.scripts] in pyproject.toml.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def _run(command: Sequence[str]) -> int:
    """Run a tool command and return its exit code."""
    try:
        result = subprocess.run(command, check=False)
        return int(result.returncode)
    except FileNotFoundError:
        tool = command[0]
        print(
            f"Missing tool '{tool}'. Install local dev extras: uv sync --extra local-dev",
            file=sys.stderr,
        )
        return 127


def run_ruff() -> None:
    """Run Ruff checks."""
    raise SystemExit(_run(["ruff", "check", "jira_cli"]))


def run_radon() -> None:
    """Run Radon complexity report."""
    raise SystemExit(_run(["radon", "cc", "jira_cli", "-s", "-a"]))


def run_pylint() -> None:
    """Run Pylint quality report."""
    raise SystemExit(_run(["pylint", "jira_cli", "-rn", "--score", "y"]))


def run_qa() -> None:
    """Run all configured QA checks in sequence."""
    checks: list[Sequence[str]] = [
        ["ruff", "check", "jira_cli"],
        ["radon", "cc", "jira_cli", "-s", "-a"],
        ["pylint", "jira_cli", "-rn", "--score", "y"],
    ]
    for check in checks:
        exit_code = _run(check)
        if exit_code != 0:
            raise SystemExit(exit_code)
