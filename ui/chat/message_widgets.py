"""
The building blocks of a conversation on screen: the user's bubble, the assistant's answer
(streaming Markdown, tool-step chips, clickable source cards), the approve/decline card for
actions, and the empty-state welcome. Display only — none of these talk to the API.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QFontMetrics, QResizeEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from models.schema import SourceRef
from ui.theme.painting import CloudGlyph

TOOL_ICONS = {"running": "⏳", "done": "✓", "failed": "⚠", "denied": "✕", "info": "ℹ"}
MAX_SOURCE_CARDS = 6
ANSWER_PADDING_PX = 8
USER_BUBBLE_MAX_WIDTH = 520
BUBBLE_PADDING_PX = 28
BUBBLE_TEXT_SLACK_PX = 8
# Must match QLabel#UserText's font-size in the stylesheet.
USER_TEXT_PX = 14
EMPTY_CLOUD_SIZE = 96


class UserBubble(QWidget):
    """The user's message, right-aligned in a rounded bubble."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        bubble = QFrame(self)
        bubble.setObjectName("UserBubble")
        label = QLabel(text, bubble)
        label.setObjectName("UserText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.addWidget(label)
        # A wrapping QLabel otherwise collapses to its narrowest width; size it to the text.
        text_width = _text_width(text, USER_TEXT_PX) + BUBBLE_TEXT_SLACK_PX
        label.setMinimumWidth(min(text_width, USER_BUBBLE_MAX_WIDTH - BUBBLE_PADDING_PX))
        bubble.setMaximumWidth(USER_BUBBLE_MAX_WIDTH)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        row.addWidget(bubble)


class AnswerText(QTextBrowser):
    """A Markdown view that grows to fit its content instead of scrolling inside the chat."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AnswerText")
        self.setOpenLinks(False)
        self.anchorClicked.connect(QDesktopServices.openUrl)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._fit_height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        """Sizes the widget to its document at the current width."""
        self.document().setTextWidth(self.viewport().width())
        self.setFixedHeight(int(self.document().size().height()) + ANSWER_PADDING_PX)


class AssistantMessage(QWidget):
    """One assistant reply: tool chips on top, the streamed answer, then source cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._markdown = ""
        self._chips: dict[str, QLabel] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 40, 0)
        self._layout.setSpacing(6)
        self._chip_column = QVBoxLayout()
        self._chip_column.setSpacing(4)
        self._layout.addLayout(self._chip_column)
        self._answer = AnswerText(self)
        self._answer.hide()
        self._layout.addWidget(self._answer)
        self._sources = QVBoxLayout()
        self._sources.setSpacing(4)
        self._layout.addLayout(self._sources)

    def append_text(self, token: str) -> None:
        """Adds streamed text and re-renders the Markdown."""
        self._markdown += token
        self._answer.show()
        self._answer.setMarkdown(self._markdown)

    def set_text(self, markdown: str) -> None:
        self._markdown = ""
        self.append_text(markdown)

    def has_text(self) -> bool:
        return bool(self._markdown.strip())

    def show_tool(self, call_id: str, label: str, status: str) -> None:
        """Adds a chip for a tool step, or updates it when the step finishes."""
        chip = self._chips.get(call_id)
        if chip is None:
            chip = QLabel(self)
            chip.setObjectName("ToolChip")
            self._chips[call_id] = chip
            row = QHBoxLayout()
            row.addWidget(chip)
            row.addStretch()
            self._chip_column.addLayout(row)
        chip.setText(f"{TOOL_ICONS.get(status, '•')}  {label}")
        chip.setProperty("status", status)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def set_sources(self, sources: list[SourceRef]) -> None:
        """Shows each source as a card that opens the file when clicked."""
        for source in sources[:MAX_SOURCE_CARDS]:
            card = QPushButton(f"📄  {source.file_name}", self)
            card.setObjectName("SourceCard")
            card.setToolTip(source.file_path)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(
                lambda _=False, path=source.file_path: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            row = QHBoxLayout()
            row.addWidget(card)
            row.addStretch()
            self._sources.addLayout(row)

    def show_error(self, message: str) -> None:
        label = QLabel(f"⚠  {message}", self)
        label.setObjectName("ErrorLine")
        label.setWordWrap(True)
        self._layout.addWidget(label)


class ConfirmCard(QFrame):
    """Asks before an action runs: Allow once, Always allow, or Don't."""

    decided = pyqtSignal(bool, bool)

    def __init__(self, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConfirmCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        question = QLabel(f"<b>Nimbus wants to:</b> {description}", self)
        question.setWordWrap(True)
        layout.addWidget(question)
        self._buttons = QHBoxLayout()
        self._add_button("Allow", "primary", approved=True, always=False)
        self._add_button("Always allow", "", approved=True, always=True)
        self._add_button("Don't", "danger", approved=False, always=False)
        self._buttons.addStretch()
        layout.addLayout(self._buttons)

    def _add_button(self, text: str, variant: str, approved: bool, always: bool) -> None:
        button = QPushButton(text, self)
        if variant:
            button.setProperty("variant", variant)
        button.clicked.connect(lambda: self._decide(approved, always))
        self._buttons.addWidget(button)

    def _decide(self, approved: bool, always: bool) -> None:
        """Locks the card so a double click can't answer twice, then reports the choice."""
        for index in range(self._buttons.count()):
            widget = self._buttons.itemAt(index).widget()
            if widget is not None:
                widget.setEnabled(False)
        self.decided.emit(approved, always)


def _text_width(text: str, pixel_size: int) -> int:
    """Width of the longest line of text at the given font size."""
    font = QFont()
    font.setPixelSize(pixel_size)
    metrics = QFontMetrics(font)
    return max(metrics.horizontalAdvance(line) for line in text.splitlines() or [""])


class EmptyState(QWidget):
    """The welcome shown in a fresh chat: a cloud, a greeting and a few things to try."""

    suggestion_clicked = pyqtSignal(str)

    def __init__(self, suggestions: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cloud = CloudGlyph(EMPTY_CLOUD_SIZE, self)
        layout.addWidget(cloud, alignment=Qt.AlignmentFlag.AlignHCenter)
        title = QLabel("Where to?", self)
        title.setObjectName("EmptyTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        hint = QLabel("Ask about your files, or tell me what to open.", self)
        hint.setProperty("role", "muted")
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        for text in suggestions:
            chip = QPushButton(text, self)
            chip.setProperty("variant", "chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, t=text: self.suggestion_clicked.emit(t))
            layout.addWidget(chip, alignment=Qt.AlignmentFlag.AlignHCenter)

    def sizeHint(self) -> QSize:
        return QSize(400, 360)
