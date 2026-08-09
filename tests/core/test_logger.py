from __future__ import annotations

import logging

from core.logger import _ContextFormatter, get_logger


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
