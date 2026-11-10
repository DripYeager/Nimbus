from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from ui.settings.section_layout import SettingsCard, ToggleRow, section_header, wrap_in_scroll_area


def _release(widget: QWidget) -> None:
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(2, 2),
        QPointF(2, 2),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)


def test_section_header_marks_title_for_display_font() -> None:
    header = section_header("Sources", "What Nimbus learns")
    assert header.findChild(QLabel, "SectionTitle").property("display") == "true"


def test_settings_card_uses_card_object_name() -> None:
    assert SettingsCard().objectName() == "Card"


def test_toggle_row_click_flips_switch() -> None:
    row = ToggleRow("Open apps", icon="app-window")
    _release(row)
    assert row.switch.isChecked()


def test_wrap_in_scroll_area_keeps_content_transparent() -> None:
    content = QWidget()
    scroll = wrap_in_scroll_area(content)
    assert scroll.widget() is content
    assert not content.autoFillBackground()
