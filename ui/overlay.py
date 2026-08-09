"""
The PyQt6 overlay window Nimbus summons on its global hotkey: an input box, a streaming
Markdown answer area, and a thinking indicator, styled and animated per Section 10.1 of
PROJECT.md. Does not talk to the query API itself — callers drive it via start_thinking(),
append_answer_token(), and show_error(), and listen for query_submitted, so this module stays
UI-only with no engine logic.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.logger import get_logger
from models.schema import SourceRef
from ui.overlay_shapes import CloudGlyph, OverlayCard
from ui.overlay_theme import (
    ACCENT_GOLD,
    ANSWER_HEIGHT,
    BOB_AMPLITUDE_PX,
    BOB_PERIOD_MS,
    CARD_PADDING,
    CARD_SPACING,
    ENTER_DURATION_MS,
    EXIT_DURATION_MS,
    INPUT_HEIGHT,
    PLACEHOLDER_TEXT,
    RISE_OFFSET_PX,
    SHADOW_BLUR_RADIUS,
    SHADOW_MARGIN,
    SHADOW_OFFSET_Y,
    SHADOW_RGBA,
    TEXT_MUTED,
    TEXT_PRIMARY,
    THINKING_TIMEOUT_MS,
    TIMEOUT_MESSAGE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)

logger = get_logger(__name__)


def _animate(widget: QWidget, prop: bytes, start: object, end: object, duration_ms: int) -> QPropertyAnimation:
    """Builds a property animation with the shared enter/exit OutCubic easing curve."""
    animation = QPropertyAnimation(widget, prop)
    animation.setDuration(duration_ms)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    return animation


class OverlayWindow(QWidget):
    """The frameless summon box: input, streaming answer, thinking indicator, Esc-to-dismiss."""

    query_submitted = pyqtSignal(str)
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._card: OverlayCard | None = None
        self._input: QLineEdit | None = None
        self._answer: QTextBrowser | None = None
        self._answer_buffer = ""
        self._glyph: CloudGlyph | None = None
        self._status_label: QLabel | None = None
        self._sources_label: QLabel | None = None
        self._bob_animation: QVariantAnimation | None = None
        self._motion_animation: QParallelAnimationGroup | None = None
        self._timeout_timer: QTimer | None = None
        self._thinking = False

    def setup(self) -> None:
        """Builds the widget tree, applies styling, and wires the Enter-key submit handler."""
        self._configure_window()
        self._build_layout()
        self._apply_styles()
        self._input.returnPressed.connect(self._handle_return_pressed)

    def is_thinking(self) -> bool:
        """True while waiting on a response — the thinking glyph is bobbing."""
        return self._thinking

    def summon(self) -> None:
        """Resets state, positions on the active screen, and plays the enter animation."""
        self._reset_state()
        final_pos = self._active_screen_center()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()
        self._play_enter(final_pos)

    def dismiss(self) -> None:
        """Stops any in-flight thinking state and plays the exit animation."""
        self._stop_thinking()
        self._play_exit()

    def start_thinking(self) -> None:
        """Clears prior state and starts the bobbing glyph with a hard timeout backstop."""
        self._answer.clear()
        self._answer_buffer = ""
        self._sources_label.clear()
        self._status_label.clear()
        self._thinking = True
        self._glyph.show()
        self._start_bob_animation()
        self._timeout_timer.start(THINKING_TIMEOUT_MS)

    def append_answer_token(self, token: str) -> None:
        """Appends streamed text to the answer; the first token proves the provider answered."""
        if self._thinking:
            self._stop_thinking()
            self._glyph.hide()
        self._answer_buffer += token
        self._answer.setMarkdown(self._answer_buffer)

    def show_error(self, message: str) -> None:
        """Freezes the glyph and shows message as a static error line, never spinning forever."""
        self._stop_thinking()
        self._glyph.show()
        self._status_label.setText(message)

    def set_sources(self, sources: list[SourceRef]) -> None:
        """Renders source file names as muted citation text below the answer."""
        self._sources_label.setText(" · ".join(source.file_name for source in sources))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Esc dismisses the overlay; everything else goes to the focused child widget."""
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(event)

    def _configure_window(self) -> None:
        """Sets frameless/always-on-top/translucent flags, a fixed size, and the timeout timer."""
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._handle_timeout)

    def _build_layout(self) -> None:
        """Wraps the card in the shadow margin and attaches its drop-shadow effect."""
        self._card = OverlayCard(self)
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(SHADOW_BLUR_RADIUS)
        shadow.setOffset(0, SHADOW_OFFSET_Y)
        shadow.setColor(QColor(*SHADOW_RGBA))
        self._card.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer.addWidget(self._card)
        self._build_card_contents()

    def _build_card_contents(self) -> None:
        """Populates the card with the input row, answer area, and status/glyph/sources rows."""
        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        layout.setSpacing(CARD_SPACING)

        self._input = QLineEdit(self._card)
        self._input.setPlaceholderText(PLACEHOLDER_TEXT)
        self._input.setFixedHeight(INPUT_HEIGHT)
        self._input.setFrame(False)

        self._answer = QTextBrowser(self._card)
        self._answer.setFixedHeight(ANSWER_HEIGHT)
        self._answer.setOpenExternalLinks(False)
        self._answer.setFrameShape(QFrame.Shape.NoFrame)

        self._glyph = CloudGlyph(self._card)
        self._status_label = QLabel(self._card)
        self._sources_label = QLabel(self._card)

        status_row = QHBoxLayout()
        status_row.addWidget(self._glyph)
        status_row.addWidget(self._status_label)
        status_row.addStretch()

        layout.addWidget(self._input)
        layout.addWidget(self._answer)
        layout.addLayout(status_row)
        layout.addWidget(self._sources_label)

    def _apply_styles(self) -> None:
        """Applies the Section 10.1 color tokens to the input, answer, and label widgets."""
        self._input.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {TEXT_PRIMARY}; font-size: 14px; }}"
            f"QLineEdit:focus {{ border-bottom: 1px solid {ACCENT_GOLD}; }}"
        )
        self._answer.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self._answer.document().setDefaultStyleSheet(
            f"body {{ color: {TEXT_PRIMARY}; font-size: 14px; line-height: 150%; }}"
        )
        self._status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        self._sources_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self._glyph.hide()

    def _play_enter(self, final_pos: QPoint) -> None:
        """Fades in and rises 8px into final_pos over 180ms, OutCubic — no overshoot."""
        start_pos = QPoint(final_pos.x(), final_pos.y() + RISE_OFFSET_PX)
        group = QParallelAnimationGroup(self)
        group.addAnimation(_animate(self, b"pos", start_pos, final_pos, ENTER_DURATION_MS))
        group.addAnimation(_animate(self, b"windowOpacity", 0.0, 1.0, ENTER_DURATION_MS))
        self._motion_animation = group
        group.start()

    def _play_exit(self) -> None:
        """The exact reverse of enter: fades out and drops 8px over 140ms, then hides."""
        start_pos = self.pos()
        end_pos = QPoint(start_pos.x(), start_pos.y() + RISE_OFFSET_PX)
        group = QParallelAnimationGroup(self)
        group.addAnimation(_animate(self, b"pos", start_pos, end_pos, EXIT_DURATION_MS))
        group.addAnimation(_animate(self, b"windowOpacity", 1.0, 0.0, EXIT_DURATION_MS))
        group.finished.connect(self._finish_dismiss)
        self._motion_animation = group
        group.start()

    def _finish_dismiss(self) -> None:
        """Hides the window once the exit animation completes and notifies listeners."""
        self.hide()
        self.dismissed.emit()

    def _start_bob_animation(self) -> None:
        """Runs the ±3px sine-like bob, looping until _stop_thinking() or the timeout fires."""
        animation = QVariantAnimation(self)
        animation.setDuration(BOB_PERIOD_MS)
        animation.setLoopCount(-1)
        animation.setKeyValueAt(0.0, 0.0)
        animation.setKeyValueAt(0.25, -float(BOB_AMPLITUDE_PX))
        animation.setKeyValueAt(0.5, 0.0)
        animation.setKeyValueAt(0.75, float(BOB_AMPLITUDE_PX))
        animation.setKeyValueAt(1.0, 0.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.valueChanged.connect(self._glyph.set_offset_y)
        self._bob_animation = animation
        animation.start()

    def _stop_thinking(self) -> None:
        """Stops the bob animation and the safety timeout so the glyph freezes, not spins forever."""
        self._thinking = False
        self._timeout_timer.stop()
        if self._bob_animation is not None:
            self._bob_animation.stop()
            self._bob_animation = None
        self._glyph.set_offset_y(0.0)

    def _handle_timeout(self) -> None:
        """Fires if start_thinking() never resolves — the glyph must not spin forever (Section 17.6)."""
        self.show_error(TIMEOUT_MESSAGE)

    def _active_screen_center(self) -> QPoint:
        """Centers the overlay on whichever screen currently holds the mouse cursor."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geometry = screen.geometry()
        x = geometry.center().x() - self.width() // 2
        y = geometry.center().y() - self.height() // 2
        return QPoint(x, y)

    def _reset_state(self) -> None:
        """Clears input, answer, sources, and status before the overlay is shown again."""
        self._input.clear()
        self._answer.clear()
        self._answer_buffer = ""
        self._sources_label.clear()
        self._status_label.clear()
        self._glyph.hide()
        self._glyph.set_offset_y(0.0)

    def _handle_return_pressed(self) -> None:
        """Emits query_submitted with the entered text, ignoring an empty box."""
        text = self._input.text().strip()
        if not text:
            return
        self.query_submitted.emit(text)
