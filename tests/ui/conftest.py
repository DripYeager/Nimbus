from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(autouse=True, scope="session")
def qapp() -> QApplication:
    """Widgets and signals need a QApplication to exist; one per test session is enough."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _flush_deferred_deletes(qapp: QApplication) -> Iterator[None]:
    """Runs each test's pending deleteLater() calls before the next test starts."""
    yield
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
