from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import core.logger as logger_module
from core.logger import LOG_FILE_NAME, LOG_FORMAT, _ContextFormatter, get_logger


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Lets _configure_root_logger() run for real against a temp log folder, then puts back
    whatever handlers the root logger had before."""
    directory = tmp_path / "logs"
    monkeypatch.setattr(logger_module, "log_dir", lambda: directory)
    monkeypatch.setattr(logger_module, "_configured", False)
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    root.handlers.clear()

    yield directory

    for handler in root.handlers:
        handler.close()
    root.handlers[:] = original_handlers


def _file_handler() -> RotatingFileHandler:
    return next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))


def _stream_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if type(h) is logging.StreamHandler]


def _nimbus_handlers() -> list[logging.Handler]:
    """Root handlers Nimbus attached — pytest adds its own log-capture handlers alongside."""
    return [h for h in logging.getLogger().handlers if type(h) in (logging.StreamHandler, RotatingFileHandler)]


def test_get_logger_returns_a_logger_with_the_given_name() -> None:
    logger = get_logger("nimbus.test")

    assert logger.name == "nimbus.test"


def test_context_formatter_appends_extra_fields() -> None:
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Indexed file", None, None)
    record.path = "C:/docs/a.txt"
    record.chunks = 3

    assert _ContextFormatter("%(message)s").format(record) == "Indexed file | path=C:/docs/a.txt chunks=3"


def test_context_formatter_leaves_a_plain_message_unchanged() -> None:
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Nimbus starting up", None, None)

    assert _ContextFormatter("%(message)s").format(record) == "Nimbus starting up"


def test_context_formatter_does_not_leak_message_or_asctime_across_shared_handlers() -> None:
    record = logging.LogRecord("nimbus.test", logging.INFO, __file__, 1, "Indexed file", None, None)
    _ContextFormatter(LOG_FORMAT).format(record)

    second = _ContextFormatter(LOG_FORMAT).format(record)

    assert "message=" not in second
    assert "asctime=" not in second


def test_get_logger_creates_the_log_file_in_the_log_dir(logs: Path) -> None:
    get_logger("nimbus.test")

    assert (logs / LOG_FILE_NAME).exists()


def test_get_logger_attaches_one_stream_and_one_rotating_file_handler(logs: Path) -> None:
    get_logger("nimbus.test")

    assert len(_stream_handlers()) == 1
    assert _file_handler() is not None


def test_get_logger_configures_the_root_logger_only_once(logs: Path) -> None:
    get_logger("nimbus.test")
    get_logger("nimbus.other")

    assert len(_nimbus_handlers()) == 2


def test_get_logger_skips_the_stdout_handler_when_there_is_no_console(
    logs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdout", None)

    get_logger("nimbus.test")

    assert [type(h) for h in _nimbus_handlers()] == [RotatingFileHandler]


def test_file_handler_uses_the_context_formatter(logs: Path) -> None:
    get_logger("nimbus.test")

    assert isinstance(_file_handler().formatter, _ContextFormatter)


def test_file_handler_has_the_configured_rotation_limits(logs: Path) -> None:
    get_logger("nimbus.test")

    handler = _file_handler()
    assert (handler.maxBytes, handler.backupCount) == (logger_module.MAX_LOG_BYTES, logger_module.LOG_BACKUP_COUNT)


def test_a_logged_message_appears_in_the_log_file_with_its_extras(logs: Path) -> None:
    get_logger("nimbus.test").info("hello from a test", extra={"path": "C:/a.txt"})
    _file_handler().flush()

    assert "hello from a test | path=C:/a.txt" in (logs / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_get_logger_raises_when_the_log_dir_cannot_be_created(logs: Path) -> None:
    logs.parent.mkdir(parents=True, exist_ok=True)
    logs.write_text("a file where the folder should be", encoding="utf-8")

    with pytest.raises(OSError):
        get_logger("nimbus.test")
