"""
Provides a single, centralized logging setup for the whole application.
Does not decide what to log or at what level — callers request a logger and log at the level they choose.
"""

from __future__ import annotations

import logging
import sys

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def _configure_root_logger() -> None:
    """Attaches a single stdout handler to the root logger, once per process."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.setLevel(DEFAULT_LOG_LEVEL)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Returns a logger for the given module, wiring up the root handler on first use."""
    _configure_root_logger()
    return logging.getLogger(name)
