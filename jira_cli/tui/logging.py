"""Optional file logging for TUI diagnostics."""

from __future__ import annotations

import logging
import os
from pathlib import Path

LOGGER_NAME = "jira_cli.tui"


def configure_tui_logging() -> Path | None:
    """Enable file logging when JIRA_TUI_LOG is configured."""
    log_path = os.environ.get("JIRA_TUI_LOG", "").strip()
    if not log_path:
        return None

    configured_level = os.environ.get("JIRA_TUI_LOG_LEVEL", "DEBUG").strip().upper()
    level = getattr(logging, configured_level, logging.DEBUG)
    if not isinstance(level, int):
        level = logging.DEBUG

    path = Path(log_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path for handler in logger.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path:
                handler.setLevel(level)
    return path


def tui_logger() -> logging.Logger:
    """Return the TUI diagnostic logger."""
    return logging.getLogger(LOGGER_NAME)
