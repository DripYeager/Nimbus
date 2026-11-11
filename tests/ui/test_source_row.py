from __future__ import annotations

from unittest.mock import Mock

from PyQt6.QtWidgets import QWidget

from models.schema import SourceSummary
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


def test_a_long_status_line_never_widens_the_row(qapp: object) -> None:
    row = SourceRow(r"C:\Users\alex\Downloads", include_contents=True)
    short_width = row.minimumSizeHint().width()
    long_name = "site_alerts_report_" + "x" * 200 + ".xlsx"

    row.set_summary(
        SourceSummary(
            path=row.path,
            include_contents=True,
            exists=True,
            file_count=11339,
            indexed_count=387,
            pending_count=10900,
            is_active=True,
            current_file=long_name,
        )
    )

    assert row.minimumSizeHint().width() == short_width
    assert long_name in row.counts_label.full_text()
    assert long_name in row.counts_label.toolTip()
