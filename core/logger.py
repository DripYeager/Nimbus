"""
Provides a single, centralized logging setup for the whole application: an INFO-level stream
to stdout and a size-capped rotating file in the per-user data folder, so a background daemon
without a visible console still leaves a trail. Does not decide what to log or at what level,
callers request a logger and log at the level they choose.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.paths import log_dir

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

LOG_FILE_NAME = "nimbus.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
QUIET_LIBRARIES = ("httpx", "httpcore", "huggingface_hub")

# message/asctime are added to a record by Formatter.format() itself, not present on a fresh
# record, but with two handlers sharing one record, the first handler's format() call bakes
# them into record.__dict__ before the second handler's format() ever runs. Excluding them here
# explicitly means correctness doesn't depend on which handler runs first.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
_configured = False
# Where console logging goes. The MCP bridge speaks its protocol on stdout, so it moves logs
# to stderr and to a file of its own (two processes rotating one file would clash).
_console_stream_name = "stdout"
_log_file_name = LOG_FILE_NAME


class _ContextFormatter(logging.Formatter):
    """Appends any extra={...} fields from a log call, otherwise they're silently dropped."""

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
    root = logging.getLogger()
    root.setLevel(DEFAULT_LOG_LEVEL)
    # A windowed build (or pythonw) has no console at all, so sys.stdout is None there.
    console = getattr(sys, _console_stream_name)
    if console is not None:
        console_handler = logging.StreamHandler(console)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    file_handler = _build_file_handler()
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    # The UI polls the local API every few seconds; one INFO line per request would bury
    # everything else in the log.
    for noisy in QUIET_LIBRARIES:
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def log_file_path() -> Path:
    """Where the current log file lives, so error messages can point people at it."""
    return log_dir() / _log_file_name


def _build_file_handler() -> RotatingFileHandler:
    """Creates the log folder if needed and returns a size-capped rotating handler over nimbus.log."""
    path = log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(path, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")


def log_beside_stdout(file_name: str) -> None:
    """For a process whose stdout is a protocol channel: logs go to stderr and file_name instead.
    Must run before the first get_logger call."""
    global _console_stream_name, _log_file_name
    _console_stream_name = "stderr"
    _log_file_name = file_name


def get_logger(name: str) -> logging.Logger:
    """Returns a logger for the given module, wiring up the root handler on first use."""
    _configure_root_logger()
    return logging.getLogger(name)
