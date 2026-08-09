"""
Provides a single, centralized logging setup for the whole application.
Does not decide what to log or at what level — callers request a logger and log at the level they choose.
"""

from __future__ import annotations

import logging
import sys

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)
_configured = False


class _ContextFormatter(logging.Formatter):
    """Appends any extra={...} fields from a log call — otherwise they're silently dropped."""

    def format(self, record: logging.LogRecord) -> str:
        # Read extras before super().format() mutates the record with its own 'message'/'asctime'.
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_RECORD_ATTRS}
        base = super().format(record)
        if not extras:
            return base
        return base + " | " + " ".join(f"{k}={v}" for k, v in extras.items())


def _configure_root_logger() -> None:
    """Attaches a single stdout handler to the root logger, once per process."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ContextFormatter(LOG_FORMAT))
    root = logging.getLogger()
    root.setLevel(DEFAULT_LOG_LEVEL)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Returns a logger for the given module, wiring up the root handler on first use."""
    _configure_root_logger()
    return logging.getLogger(name)
