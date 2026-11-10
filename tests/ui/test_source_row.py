from __future__ import annotations

from unittest.mock import Mock

from PyQt6.QtWidgets import QWidget

from ui.settings.source_row import SourceRow


def test_source_row_to_setting_reflects_switch() -> None:
    row = SourceRow("C:/Users/me/Documents", include_contents=True)
    row.contents_switch.setChecked(False)
    assert row.to_setting() == {"path": "C:/Users/me/Documents", "include_contents": False}


def test_source_row_remove_emits_itself() -> None:
    row = SourceRow("D:/Media", include_contents=False)
    removed = Mock()
    row.remove_requested.connect(removed)
    row.findChild(QWidget, "IconButton").click()
    removed.assert_called_once_with(row)
