from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True, scope="session")
def qapp() -> QApplication:
    """Widgets and signals need a QApplication to exist; one per test session is enough."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_background_ollama_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Model page's Ollama card checks the engine on its own; in tests that would hit a fake
    API from a worker thread. Tests of the card itself patch this again to drive it."""
    monkeypatch.setattr("ui.settings.ollama_helper.run_in_background", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _flush_deferred_deletes(qapp: QApplication) -> Iterator[None]:
    """Runs each test's pending deleteLater() calls before the next test starts."""
    yield
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


@pytest.fixture(autouse=True)
def _no_real_explorer_menu(mocker: MockerFixture) -> None:
    """Settings tests must never write to the real registry."""
    mocker.patch("ui.settings.general_tab.is_explorer_menu_enabled", return_value=False)
    mocker.patch("ui.settings.general_tab.enable_explorer_menu")
    mocker.patch("ui.settings.general_tab.disable_explorer_menu")
