from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

import ui.background_call as background_call
from core.exceptions import NimbusError
from ui.background_call import run_in_background


def _settle() -> None:
    """Lets the pool finish, then delivers the queued result signals on this (GUI) thread."""
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def _raise(error: Exception) -> Any:
    raise error


def test_run_in_background_delivers_the_result() -> None:
    results: list[Any] = []

    run_in_background(lambda: 42, results.append, results.append)
    _settle()

    assert results == [42]


def test_run_in_background_reports_nimbus_errors_verbatim() -> None:
    errors: list[str] = []

    run_in_background(lambda: _raise(NimbusError("Folder not found")), errors.append, errors.append)
    _settle()

    assert errors == ["Folder not found"]


def test_run_in_background_reports_unexpected_errors() -> None:
    errors: list[str] = []

    run_in_background(lambda: _raise(ValueError("boom")), errors.append, errors.append)
    _settle()

    assert errors == ["Unexpected error: boom"]


def test_run_in_background_ignores_failures_without_an_error_callback() -> None:
    results: list[Any] = []

    run_in_background(lambda: _raise(NimbusError("nope")), results.append)
    _settle()

    assert results == []


def test_run_in_background_releases_the_call_once_it_reports() -> None:
    run_in_background(lambda: None, lambda _: None)
    run_in_background(lambda: _raise(NimbusError("nope")), lambda _: None)
    _settle()

    assert background_call._in_flight == set()
