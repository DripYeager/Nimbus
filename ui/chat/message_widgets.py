"""
The two kinds of message on screen: the user's orange speech bubble, and Nimbus's reply, an
energy-orb avatar that pulses while it's thinking, the activity steps, the streamed Markdown
answer, source cards and a copy button. Display only; neither talks to the API.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QIcon, QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from models.schema import SourceRef
from ui.chat.answer_style import clean_answer
from ui.chat.code_block import StepDetail
from ui.chat.message_cards import SourceCard, ToolStep
from ui.chat.thinking_indicator import ThinkingIndicator
from ui.theme.energy import EnergyOrb
from ui.theme.line_icons import line_icon
from ui.theme.tokens import SUCCESS, TEXT, TEXT_MUTED

MAX_SOURCE_CARDS = 6
ANSWER_PADDING_PX = 6
AVATAR_SIZE = 34
COPY_ICON_SIZE = 15
COPIED_FEEDBACK_MS = 1500
STOPPED_TEXT = "Stopped."


# How often a streaming answer is redrawn.
RENDER_INTERVAL_MS = 60


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
        # Text after a tool step starts a new paragraph, not glued to the text before it.
        self._break_before_text = False
        # Streaming re-renders at most this often: parsing the whole answer per token made long
        # answers slower and slower to draw.
        self._render_timer = _single_shot(self, RENDER_INTERVAL_MS, self._render)
        self._avatar = EnergyOrb(AVATAR_SIZE, self)
        self._thinking = ThinkingIndicator(self)
        self._copy = _copy_button(self)
        self._copy.clicked.connect(self._copy_answer)
        self._copied_reset = _single_shot(self, COPIED_FEEDBACK_MS, lambda: self._copy.setIcon(_copy_icon()))
        self._copy.hide()
        self._answer = AnswerText(self)
        self._answer.hide()
        self._build_layout()

    def _build_layout(self) -> None:
        """Author row, thinking line, steps, answer and sources beside the avatar."""
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
        """Adds streamed text; the Markdown is redrawn shortly after, at most every
        RENDER_INTERVAL_MS, so a long answer streams as smoothly as a short one."""
        self.stop_thinking()
        if self._break_before_text and token.strip() and self._markdown.strip():
            self._markdown = self._markdown.rstrip() + "\n\n"
            token = token.lstrip()
        self._break_before_text = self._break_before_text and not token.strip()
        self._markdown += token
        self._answer.show()
        self._copy.show()
        if not self._render_timer.isActive():
            self._render_timer.start()

    def set_text(self, markdown: str) -> None:
        self._markdown = ""
        self.append_text(markdown)
        self.flush()

    def flush(self) -> None:
        """Draws any text still waiting for the next render (the reply ended, say)."""
        if self._render_timer.isActive():
            self._render_timer.stop()
            self._render()

    def _render(self) -> None:
        self._answer.setMarkdown(clean_answer(self._markdown))

    def settle_steps(self, status: str) -> None:
        """Steps still spinning when the reply ends (stopped, failed) stop spinning."""
        for step in self._steps.values():
            if step.status == "running":
                step.update_step(step.label, status)

    def has_text(self) -> bool:
        return bool(self._markdown.strip())

    def is_empty(self) -> bool:
        """True when nothing but the thinking state was ever shown."""
        return not self.has_text() and not self._steps and not self._has_error and self._sources.count() == 0

    def show_tool(self, call_id: str, label: str, status: str, detail: StepDetail | None = None) -> None:
        """Adds a step to the activity log, or updates it when the step finishes."""
        step = self._steps.get(call_id)
        if step is None:
            step = ToolStep(self)
            self._steps[call_id] = step
            self._steps_column.addWidget(step)
        step.update_step(label, status)
        if detail is not None:
            step.show_detail(detail)
        if self._markdown.strip():
            self._break_before_text = True

    def set_sources(self, sources: list[SourceRef]) -> None:
        for source in sources[:MAX_SOURCE_CARDS]:
            self._sources.addWidget(SourceCard(source, self))

    def show_error(self, message: str) -> None:
        self.stop_thinking()
        self.flush()
        self.settle_steps("failed")
        self._has_error = True
        label = QLabel(message, self)
        label.setObjectName("ErrorLine")
        label.setWordWrap(True)
        self._content.insertWidget(self._content.count() - 1, label)

    def mark_stopped(self) -> None:
        """Ends the reply where it is, with a quiet note that the user stopped it."""
        self.stop_thinking()
        self.flush()
        self.settle_steps("stopped")
        self._has_error = True
        label = QLabel(STOPPED_TEXT, self)
        label.setObjectName("StoppedLine")
        self._content.insertWidget(self._content.count() - 1, label)

    def _author_row(self) -> QHBoxLayout:
        """ "Nimbus · 10:42" with the copy button at the far end."""
        author = QLabel("Nimbus", self)
        author.setObjectName("ReplyAuthor")
        self._time = QLabel(datetime.now().strftime("%H:%M"), self)
        self._time.setObjectName("ReplyMeta")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(author)
        row.addWidget(self._time)
        row.addStretch()
        row.addWidget(self._copy)
        return row

    def hide_time(self) -> None:
        """For a reopened chat: saved messages don't record when they were written, so no time
        is better than today's."""
        self._time.hide()

    def _copy_answer(self) -> None:
        """Copies the answer's Markdown and flashes a check mark."""
        QGuiApplication.clipboard().setText(clean_answer(self._markdown))
        self._copy.setIcon(line_icon("check", SUCCESS, COPY_ICON_SIZE))
        self._copied_reset.start()


def _single_shot(parent: QWidget, interval_ms: int, slot: Callable[[], object]) -> QTimer:
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(slot)
    return timer


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
