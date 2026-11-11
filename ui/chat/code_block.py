"""
The block that shows code or a command a step runs, and what it printed: a few lines at first,
with "Show all" to open the rest (clicking the block does the same) and a Copy button. Used
under a step in a reply and on the approval card, so the user always sees what will run.
Display only; nothing here runs anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QMouseEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from models.chat import ShownCode

PREVIEW_LINES = 5
# A single very long line (a one-line command, say) is cut too, not only many lines.
PREVIEW_CHARS = 360
MORE_MARK = "\n..."
COPY_TEXT = "Copy"
COPIED_TEXT = "Copied"
COPIED_RESET_MS = 1500
LESS_TEXT = "Show less"
OUTPUT_TITLE = "Output"


@dataclass(frozen=True)
class StepDetail:
    """What a step shows under its line: the code it runs and, once finished, its output."""

    code: ShownCode | None = None
    output: str | None = None


def preview_of(text: str) -> str:
    """The first few lines (and characters) of text, marked when there's more."""
    lines = text.splitlines()
    preview = "\n".join(lines[:PREVIEW_LINES])
    if len(preview) > PREVIEW_CHARS:
        preview = preview[:PREVIEW_CHARS].rstrip()
    return preview + (MORE_MARK if preview != text.strip() else "")


def show_all_text(text: str) -> str:
    count = len(text.splitlines())
    return f"Show all {count} lines" if count > 1 else "Show all"


class CodeBlock(QFrame):
    """A titled, monospaced, collapsible view of code or output."""

    def __init__(self, code: ShownCode, parent: QWidget | None = None, full_if_one_line: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("CodeBlock")
        self._full = code.text
        # On an approval card a one-line command is shown whole: padding could push a second
        # command past the preview's cut. Longer code says how many lines are hidden.
        one_line = len(code.text.strip().splitlines()) <= 1
        self._preview = code.text.strip() if full_if_one_line and one_line else preview_of(code.text)
        self._expanded = False
        self._text = QLabel(self._preview, self)
        self._text.setObjectName("CodeText")
        self._text.setWordWrap(True)
        self._text.setTextFormat(Qt.TextFormat.PlainText)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._toggle = _link_button(show_all_text(code.text), self)
        self._toggle.setVisible(self.can_expand())
        self._copy = _link_button(COPY_TEXT, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        layout.addLayout(self._header(code.title))
        layout.addWidget(self._text)
        self._toggle.clicked.connect(self.toggle)
        self._copy.clicked.connect(self._copy_all)
        # Owned by the block: a free timer would still fire after the block was deleted
        # (the user copied, then switched chats) and touch a widget that is already gone.
        self._copied_reset = _owned_single_shot(self, COPIED_RESET_MS, self._reset_copy)
        if self.can_expand():
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _header(self, title: str) -> QHBoxLayout:
        label = QLabel(title, self)
        label.setObjectName("CodeTitle")
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(self._toggle)
        header.addWidget(self._copy)
        return header

    def can_expand(self) -> bool:
        return self._preview != self._full.strip()

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        if not self.can_expand():
            return
        self._expanded = not self._expanded
        self._text.setText(self._full if self._expanded else self._preview)
        self._toggle.setText(LESS_TEXT if self._expanded else show_all_text(self._full))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """A click on the block opens or closes it (selecting text inside doesn't)."""
        if event.button() == Qt.MouseButton.LeftButton and not self._text.hasSelectedText():
            self.toggle()
        super().mouseReleaseEvent(event)

    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self._full)
        self._copy.setText(COPIED_TEXT)
        self._copied_reset.start()

    def _reset_copy(self) -> None:
        self._copy.setText(COPY_TEXT)


def _owned_single_shot(owner: QWidget, interval_ms: int, slot: object) -> QTimer:
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(slot)
    return timer


def output_block(text: str, parent: QWidget | None = None) -> CodeBlock:
    return CodeBlock(ShownCode(title=OUTPUT_TITLE, text=text.strip() or "(nothing printed)"), parent)


def _link_button(text: str, parent: QWidget) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName("CodeLink")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFlat(True)
    return button
