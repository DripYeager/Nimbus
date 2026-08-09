from __future__ import annotations

import logging
import shutil
from logging.handlers import RotatingFileHandler

import pytest

import core.logger as logger_module
from core.logger import LOG_FORMAT, _ContextFormatter, get_logger


@pytest.fixture
def clean_logging_state():
    """Resets the root logger to its pre-configuration state so _configure_root_logger() runs
    for real, then restores whatever was there before and removes any logs/ it created."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_configured = logger_module._configured
    root.handlers.clear()
    logger_module._configured = False
    shutil.rmtree(logger_module.LOG_DIR, ignore_errors=True)

    yield

    for handler in root.handlers:
        handler.close()
    root.handlers.clear()
    root.handlers.extend(original_handlers)
    logger_module._configured = original_configured
    shutil.rmtree(logger_module.LOG_DIR, ignore_errors=True)


def test_get_logger_returns_a_logger_with_the_given_name() -> None:
    logger = get_logger("nimbus.test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "nimbus.test"


def test_context_formatter_appends_extra_fields() -> None:
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Indexed file", None, None)
    record.path = "C:/docs/a.txt"
    record.chunks = 3
    output = _ContextFormatter("%(message)s").format(record)
    assert output == "Indexed file | path=C:/docs/a.txt chunks=3"


def test_context_formatter_leaves_a_plain_message_unchanged() -> None:
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Nimbus starting up", None, None)
    assert _ContextFormatter("%(message)s").format(record) == "Nimbus starting up"


def test_context_formatter_does_not_leak_message_or_asctime_across_shared_handlers() -> None:
    """Reproduces the real bug: two handlers on the same logger receive the SAME LogRecord.
    The first handler's format() call bakes message/asctime into record.__dict__, and the
    second handler's format() call must not misread those as extra fields."""
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Indexed file", None, None)
    stdout_formatter = _ContextFormatter(LOG_FORMAT)
    file_formatter = _ContextFormatter(LOG_FORMAT)

    first_output = stdout_formatter.format(record)
    second_output = file_formatter.format(record)

    for output in (first_output, second_output):
        assert "message=" not in output
        assert "asctime=" not in output


def test_configure_root_logger_creates_the_logs_directory(clean_logging_state) -> None:
    get_logger("nimbus.test")

    assert logger_module.LOG_DIR.is_dir()
    assert logger_module.LOG_FILE.exists()


def test_configure_root_logger_attaches_a_stream_and_a_rotating_file_handler(clean_logging_state) -> None:
    get_logger("nimbus.test")

    root = logging.getLogger()
    assert sum(type(h) is logging.StreamHandler for h in root.handlers) == 1
    assert sum(isinstance(h, RotatingFileHandler) for h in root.handlers) == 1


def test_configure_root_logger_is_idempotent(clean_logging_state) -> None:
    get_logger("nimbus.test")
    get_logger("nimbus.other")

    root = logging.getLogger()
    assert sum(type(h) is logging.StreamHandler for h in root.handlers) == 1
    assert sum(isinstance(h, RotatingFileHandler) for h in root.handlers) == 1


def test_file_handler_uses_the_context_formatter(clean_logging_state) -> None:
    get_logger("nimbus.test")

    file_handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert isinstance(file_handler.formatter, _ContextFormatter)


def test_file_handler_has_the_configured_rotation_limits(clean_logging_state) -> None:
    get_logger("nimbus.test")

    file_handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert file_handler.maxBytes == logger_module.MAX_LOG_BYTES
    assert file_handler.backupCount == logger_module.LOG_BACKUP_COUNT


def test_a_logged_message_actually_appears_in_the_log_file(clean_logging_state) -> None:
    test_logger = get_logger("nimbus.test")

    test_logger.info("hello from a test")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "hello from a test" in logger_module.LOG_FILE.read_text(encoding="utf-8")
