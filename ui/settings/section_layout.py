"""
Shared building blocks for the Settings and onboarding screens: display-font headings, group
titles, rounded cards, switch rows, icons and the scroll wrapper. Owns structure and spacing
only; colours and shapes come from settings_styles.py through the object names set here.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.settings.label_roles import styled_label
from ui.theme.fonts import use_display_font
from ui.theme.line_icons import line_pixmap
from ui.theme.tokens import ICON_SIZE, TEXT_MUTED
from ui.widgets.toggle_switch import ToggleSwitch

# Everything on these screens sits on an 8px grid.
GAP = 8
CARD_PADDING = 16
CARD_ROW_SPACING = 12
GROUP_SPACING = 24
SECTION_TITLE_PX = 24
ICON_TILE_SIZE = 36


def section_header(title: str, description: str, title_px: int = SECTION_TITLE_PX) -> QWidget:
    """A display-font heading with its one-line explanation beneath."""
    heading = QLabel(title)
    heading.setObjectName("SectionTitle")
    use_display_font(heading, title_px)
    return _stacked(heading, styled_label(description, "muted", wrap=True))


def group_header(title: str, hint: str = "") -> QWidget:
    """The small title (and optional hint) above a card or a list of cards."""
    heading = QLabel(title)
    heading.setObjectName("GroupTitle")
    return _stacked(heading, styled_label(hint, "muted", wrap=True)) if hint else _stacked(heading)


def _stacked(*widgets: QWidget) -> QWidget:
    """Widgets in a tight column with no outer margin."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(GAP // 2)
    for widget in widgets:
        layout.addWidget(widget)
    return holder


def icon_label(name: str, color: str = TEXT_MUTED, size: int = ICON_SIZE) -> QLabel:
    """A fixed-size label showing one tinted line icon."""
    label = QLabel()
    label.setPixmap(line_pixmap(name, color, size))
    label.setFixedSize(size, size)
    return label


def icon_tile(name: str, color: str) -> QLabel:
    """An icon centred on a small rounded tile, the leading mark of folder and provider cards."""
    tile = QLabel()
    tile.setObjectName("IconTile")
    tile.setPixmap(line_pixmap(name, color, ICON_SIZE))
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tile.setFixedSize(ICON_TILE_SIZE, ICON_TILE_SIZE)
    return tile


def two_state_icon(name: str, off_color: str, on_color: str) -> QIcon:
    """An icon that switches colour with a checkable button's state."""
    icon = QIcon()
    icon.addPixmap(line_pixmap(name, off_color, ICON_SIZE), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(line_pixmap(name, on_color, ICON_SIZE), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def divider() -> QFrame:
    """A hairline between rows inside a card."""
    line = QFrame()
    line.setObjectName("CardDivider")
    line.setFixedHeight(1)
    return line


def wrap_in_scroll_area(content: QWidget) -> QScrollArea:
    """A frameless, vertical-only scroll area that keeps the night background showing through."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    # setWidget turns auto-fill on, which paints the platform palette over the night theme.
    content.setAutoFillBackground(False)
    scroll.viewport().setAutoFillBackground(False)
    return scroll


def labelled_row(icon: str, title: str, detail: QLabel, control: QWidget) -> QHBoxLayout:
    """Icon, a title over a muted detail line, and a control on the right."""
    title_label = QLabel(title)
    title_label.setObjectName("RowTitle")
    text_column = QVBoxLayout()
    text_column.setSpacing(2)
    text_column.addWidget(title_label)
    text_column.addWidget(detail)
    row = QHBoxLayout()
    row.setSpacing(CARD_ROW_SPACING)
    row.addWidget(icon_label(icon))
    row.addLayout(text_column, 1)
    row.addWidget(control)
    return row


class SettingsCard(QFrame):
    """A rounded surface grouping related controls; callers add rows to body."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        self.body.setSpacing(CARD_ROW_SPACING)


class ToggleRow(QWidget):
    """A label (with optional icon and hint) on the left and a switch on the right. Clicking
    anywhere on the row flips the switch, like clicking a checkbox's text."""

    def __init__(self, text: str, *, icon: str | None = None, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.switch = ToggleSwitch()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        title = QLabel(text)
        title.setObjectName("RowTitle")
        text_column = _stacked(title, styled_label(hint, "muted", wrap=True)) if hint else _stacked(title)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CARD_ROW_SPACING)
        if icon:
            layout.addWidget(icon_label(icon))
        layout.addWidget(text_column, 1)
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.switch.isEnabled():
            self.switch.toggle()
        super().mouseReleaseEvent(event)
