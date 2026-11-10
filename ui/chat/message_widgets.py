"""
The two kinds of message on screen: the user's orange speech bubble, and Nimbus's reply, an
energy-orb avatar that pulses while it's thinking, the activity steps, the streamed Markdown
answer, source cards and a copy button. Display only; neither talks to the API.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QDesktopServices, QFont, QFontMetrics, QGuiApplication, QIcon, QResizeEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from core.attachment_format import AttachedItem
from models.schema import SourceRef
from ui.chat.answer_style import remove_dashes
from ui.chat.attachment_preview import image_preview
from ui.chat.message_cards import SourceCard, ToolStep
from ui.chat.thinking_indicator import ThinkingIndicator
from ui.theme.energy import EnergyOrb
from ui.theme.line_icons import line_icon, line_pixmap
from ui.theme.tokens import SUCCESS, TEXT, TEXT_MUTED, TEXT_ON_ORANGE

MAX_SOURCE_CARDS = 6
ANSWER_PADDING_PX = 6
USER_BUBBLE_MAX_WIDTH = 520
BUBBLE_PADDING_PX = 32
BUBBLE_TEXT_SLACK_PX = 8
# Must match QLabel#UserText's font-size in the stylesheet.
USER_TEXT_PX = 14
AVATAR_SIZE = 34
COPY_ICON_SIZE = 15
TAG_ICON_SIZE = 13
BUBBLE_PREVIEW_WIDTH = 260
BUBBLE_PREVIEW_HEIGHT = 170
COPIED_FEEDBACK_MS = 1500
STOPPED_TEXT = "Stopped."


class UserBubble(QWidget):
    """The user's message, right-aligned in a gi-orange bubble, with a tag for each attachment."""

    def __init__(self, text: str, parent: QWidget | None = None, attachments: tuple[AttachedItem, ...] = ()) -> None:
        super().__init__(parent)
        bubble = QFrame(self)
        bubble.setObjectName("UserBubble")
        label = QLabel(text, bubble)
        label.setObjectName("UserText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # A wrapping QLabel otherwise collapses to its narrowest width; size it to the text.
        text_width = _text_width(text, USER_TEXT_PX) + BUBBLE_TEXT_SLACK_PX
        label.setMinimumWidth(min(text_width, USER_BUBBLE_MAX_WIDTH - BUBBLE_PADDING_PX))
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(16, 10, 16, 10)
        inner.addWidget(label)
        for item in attachments:
            preview = image_preview(item.path, BUBBLE_PREVIEW_WIDTH, BUBBLE_PREVIEW_HEIGHT, bubble)
            if preview is not None:
                inner.addWidget(preview)
            inner.addLayout(_attachment_tag(item.name, bubble))
        bubble.setMaximumWidth(USER_BUBBLE_MAX_WIDTH)
        row = QHBoxLayout(self)
        row.setContentsMargins(60, 0, 0, 0)
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
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(f"a {{ color: {SUCCESS}; }} code {{ color: {TEXT}; }}")
        self.document().contentsChanged.connect(self._fit_height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        """Sizes the widget to its document at the current width."""
        self.document().setTextWidth(self.viewport().width())
        self.setFixedHeight(int(self.document().size().height()) + ANSWER_PADDING_PX)


class AssistantMessage(QWidget):
    """One reply. Starts in the thinking state when created for a new question."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._markdown = ""
        self._steps: dict[str, ToolStep] = {}
        self._has_error = False
        self._avatar = EnergyOrb(AVATAR_SIZE, self)
        self._thinking = ThinkingIndicator(self)
        self._copy = _copy_button(self)
        self._copy.clicked.connect(self._copy_answer)
        self._copied_reset = QTimer(self)
        self._copied_reset.setSingleShot(True)
        self._copied_reset.setInterval(COPIED_FEEDBACK_MS)
        self._copied_reset.timeout.connect(lambda: self._copy.setIcon(_copy_icon()))
        self._copy.hide()
        self._answer = AnswerText(self)
        self._answer.hide()
        self._content = QVBoxLayout()
        self._content.setSpacing(6)
        self._content.addLayout(self._author_row())
        self._content.addWidget(self._thinking)
        self._steps_column = QVBoxLayout()
        self._steps_column.setSpacing(2)
        self._content.addLayout(self._steps_column)
        self._content.addWidget(self._answer)
        self._sources = QVBoxLayout()
        self._sources.setSpacing(6)
        self._content.addLayout(self._sources)
        # Spare height (the answer view briefly over-measures as text starts streaming) goes
        # below the reply, not into gaps between the activity steps.
        self._content.addStretch(1)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 40, 0)
        row.setSpacing(12)
        row.addWidget(self._avatar, alignment=Qt.AlignmentFlag.AlignTop)
        row.addLayout(self._content, stretch=1)

    def start_thinking(self) -> None:
        self._thinking.start()
        self._avatar.start()

    def stop_thinking(self) -> None:
        self._thinking.stop()
        self._avatar.stop()

    def append_text(self, token: str) -> None:
        """Adds streamed text and re-renders the Markdown."""
        self.stop_thinking()
        self._markdown += token
        self._answer.show()
        self._copy.show()
        self._answer.setMarkdown(remove_dashes(self._markdown))

    def set_text(self, markdown: str) -> None:
        self._markdown = ""
        self.append_text(markdown)

    def has_text(self) -> bool:
        return bool(self._markdown.strip())

    def is_empty(self) -> bool:
        """True when nothing but the thinking state was ever shown."""
        return not self.has_text() and not self._steps and not self._has_error and self._sources.count() == 0

    def show_tool(self, call_id: str, label: str, status: str) -> None:
        """Adds a step to the activity log, or updates it when the step finishes."""
        step = self._steps.get(call_id)
        if step is None:
            step = ToolStep(self)
            self._steps[call_id] = step
            self._steps_column.addWidget(step)
        step.update_step(label, status)

    def set_sources(self, sources: list[SourceRef]) -> None:
        for source in sources[:MAX_SOURCE_CARDS]:
            self._sources.addWidget(SourceCard(source, self))

    def show_error(self, message: str) -> None:
        self.stop_thinking()
        self._has_error = True
        label = QLabel(message, self)
        label.setObjectName("ErrorLine")
        label.setWordWrap(True)
        self._content.insertWidget(self._content.count() - 1, label)

    def mark_stopped(self) -> None:
        """Ends the reply where it is, with a quiet note that the user stopped it."""
        self.stop_thinking()
        self._has_error = True
        label = QLabel(STOPPED_TEXT, self)
        label.setObjectName("StoppedLine")
        self._content.insertWidget(self._content.count() - 1, label)

    def _author_row(self) -> QHBoxLayout:
        """ "Nimbus · 10:42" with the copy button at the far end."""
        author = QLabel("Nimbus", self)
        author.setObjectName("ReplyAuthor")
        meta = QLabel(datetime.now().strftime("%H:%M"), self)
        meta.setObjectName("ReplyMeta")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(author)
        row.addWidget(meta)
        row.addStretch()
        row.addWidget(self._copy)
        return row

    def _copy_answer(self) -> None:
        """Copies the answer's Markdown and flashes a check mark."""
        QGuiApplication.clipboard().setText(remove_dashes(self._markdown))
        self._copy.setIcon(line_icon("check", SUCCESS, COPY_ICON_SIZE))
        self._copied_reset.start()


def _attachment_tag(name: str, parent: QWidget) -> QHBoxLayout:
    """A paperclip and the attachment's name, inside the user's bubble."""
    icon = QLabel(parent)
    icon.setPixmap(line_pixmap("paperclip", TEXT_ON_ORANGE, TAG_ICON_SIZE))
    label = QLabel(name, parent)
    label.setObjectName("AttachmentTag")
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addWidget(icon)
    row.addWidget(label)
    row.addStretch()
    return row


def _copy_icon() -> QIcon:
    return line_icon("copy", TEXT_MUTED, COPY_ICON_SIZE, hover_color=TEXT)


def _copy_button(parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName("MessageAction")
    button.setIcon(_copy_icon())
    button.setIconSize(QSize(COPY_ICON_SIZE, COPY_ICON_SIZE))
    button.setToolTip("Copy answer")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _text_width(text: str, pixel_size: int) -> int:
    """Width of the longest line of text at the given font size."""
    font = QFont()
    font.setPixelSize(pixel_size)
    metrics = QFontMetrics(font)
    return max(metrics.horizontalAdvance(line) for line in text.splitlines() or [""])
