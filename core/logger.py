"""
Provides a single, centralized logging setup for the whole application: an INFO-level stream
to stdout and a size-capped rotating file under logs/ at the repo root, so a background daemon
without a visible console still leaves a trail. Does not decide what to log or at what level —
callers request a logger and log at the level they choose.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "nimbus.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# message/asctime are added to a record by Formatter.format() itself, not present on a fresh
# record — but with two handlers sharing one record, the first handler's format() call bakes
# them into record.__dict__ before the second handler's format() ever runs. Excluding them here
# explicitly means correctness doesn't depend on which handler runs first.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
_configured = False


class _ContextFormatter(logging.Formatter):
    """Appends any extra={...} fields from a log call — otherwise they're silently dropped."""

    def format(self, record: logging.LogRecord) -> str:
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_RECORD_ATTRS}
        base = super().format(record)
        if not extras:
            return base
        return base + " | " + " ".join(f"{k}={v}" for k, v in extras.items())


def _configure_root_logger() -> None:
    """Attaches a stdout handler and a rotating file handler to the root logger, once per process."""
    global _configured
    if _configured:
        return
    formatter = _ContextFormatter(LOG_FORMAT)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    file_handler = _build_file_handler()
    file_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(DEFAULT_LOG_LEVEL)
    root.addHandler(stdout_handler)
    root.addHandler(file_handler)
    _configured = True


def _build_file_handler() -> RotatingFileHandler:
    """Creates logs/ if needed and returns a size-capped rotating file handler over nimbus.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")


def get_logger(name: str) -> logging.Logger:
    """Returns a logger for the given module, wiring up the root handler on first use."""
    _configure_root_logger()
    return logging.getLogger(name)
