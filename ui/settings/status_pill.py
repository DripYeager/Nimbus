"""
A rounded result pill, icon plus short message, for outcomes like a connection test. Owns
showing one state at a time (busy, ok, error); what the message says is the caller's call.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from ui.settings.label_roles import set_state
from ui.theme.line_icons import line_pixmap
from ui.theme.tokens import DANGER, SUCCESS, TEXT_MUTED

PILL_ICON_SIZE = 14
PILL_MARGINS = (10, 4, 12, 4)
PILL_SPACING = 6
PILL_ICONS: dict[str, tuple[str, str]] = {
    "busy": ("loader-circle", TEXT_MUTED),
    "ok": ("check", SUCCESS),
    "error": ("circle-alert", DANGER),
}


class StatusPill(QFrame):
    """Hidden until show_status() is called; clear() hides it again."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPill")
        self._icon = QLabel()
        self._icon.setFixedSize(PILL_ICON_SIZE, PILL_ICON_SIZE)
        self._text = QLabel()
        self._text.setObjectName("StatusPillText")
        self._text.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*PILL_MARGINS)
        layout.setSpacing(PILL_SPACING)
        layout.addWidget(self._icon)
        layout.addWidget(self._text, 1)
        self.hide()

    def show_status(self, text: str, state: str) -> None:
        """Shows text with the icon and colours for state ("busy", "ok" or "error")."""
        name, color = PILL_ICONS[state]
        self._icon.setPixmap(line_pixmap(name, color, PILL_ICON_SIZE))
        self._text.setText(text)
        set_state(self, state)
        set_state(self._text, state)
        self.show()

    def clear(self) -> None:
        self._text.clear()
        self.hide()

    def text(self) -> str:
        return self._text.text()

    def state(self) -> str:
        return str(self.property("state") or "")
