from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(autouse=True, scope="session")
def qapp() -> QApplication:
    """Widgets and signals need a QApplication to exist; one per test session is enough."""
    return QApplication.instance() or QApplication([])
