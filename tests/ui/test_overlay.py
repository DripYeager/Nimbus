from __future__ import annotations

import pytest
from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent

from models.schema import SourceRef
from ui.overlay import OverlayWindow
from ui.overlay_theme import ENTER_DURATION_MS, EXIT_DURATION_MS


@pytest.fixture(autouse=True, scope="session")
def _qapp():
    """QWidget/pyqtSignal machinery needs a QApplication instance to exist somewhere."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def window():
    overlay = OverlayWindow()
    overlay.setup()
    yield overlay
    overlay.deleteLater()


def test_handle_return_pressed_emits_query_submitted_with_text(window: OverlayWindow) -> None:
    received = []
    window.query_submitted.connect(received.append)
    window._input.setText("find the invoice pdf")

    window._handle_return_pressed()

    assert received == ["find the invoice pdf"]


def test_handle_return_pressed_ignores_empty_input(window: OverlayWindow) -> None:
    received = []
    window.query_submitted.connect(received.append)
    window._input.setText("   ")

    window._handle_return_pressed()

    assert received == []


def test_start_thinking_sets_is_thinking_true_and_shows_glyph(window: OverlayWindow) -> None:
    window.start_thinking()

    assert window.is_thinking() is True
    assert not window._glyph.isHidden()


def test_append_answer_token_stops_thinking_on_first_token(window: OverlayWindow) -> None:
    window.start_thinking()

    window.append_answer_token("Hello")

    assert window.is_thinking() is False
    assert window._glyph.isHidden()


def test_append_answer_token_accumulates_markdown_text(window: OverlayWindow) -> None:
    window.start_thinking()

    window.append_answer_token("**bold**")
    window.append_answer_token(" and more")

    assert window._answer_buffer == "**bold** and more"


def test_show_error_stops_thinking_and_sets_status_text(window: OverlayWindow) -> None:
    window.start_thinking()

    window.show_error("Ollama is offline")

    assert window.is_thinking() is False
    assert window._status_label.text() == "Ollama is offline"


def test_show_error_keeps_the_glyph_visible_but_frozen(window: OverlayWindow) -> None:
    window.start_thinking()

    window.show_error("Ollama is offline")

    assert not window._glyph.isHidden()
    assert window._glyph._offset_y == 0.0


def test_handle_timeout_shows_the_timeout_message(window: OverlayWindow) -> None:
    window.start_thinking()

    window._handle_timeout()

    assert window.is_thinking() is False
    assert "didn't hear back" in window._status_label.text()


def test_set_sources_renders_muted_file_names(window: OverlayWindow) -> None:
    sources = [
        SourceRef(file_name="invoice.pdf", file_path="C:/invoice.pdf", score=0.9),
        SourceRef(file_name="report.docx", file_path="C:/report.docx", score=0.7),
    ]

    window.set_sources(sources)

    assert window._sources_label.text() == "invoice.pdf · report.docx"


def test_key_press_event_escape_calls_dismiss(window: OverlayWindow, mocker) -> None:
    dismiss = mocker.patch.object(window, "dismiss")
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)

    window.keyPressEvent(event)

    dismiss.assert_called_once()


def test_play_enter_builds_a_180ms_outcubic_animation_pair(window: OverlayWindow) -> None:
    window._play_enter(QPoint(100, 100))

    group = window._motion_animation
    assert group.animationCount() == 2
    for i in range(2):
        animation = group.animationAt(i)
        assert animation.duration() == ENTER_DURATION_MS
        assert animation.easingCurve().type() == QEasingCurve.Type.OutCubic


def test_play_exit_builds_a_140ms_animation_pair(window: OverlayWindow) -> None:
    window._play_exit()

    group = window._motion_animation
    assert group.animationCount() == 2
    for i in range(2):
        assert group.animationAt(i).duration() == EXIT_DURATION_MS


def test_finish_dismiss_hides_window_and_emits_dismissed(window: OverlayWindow) -> None:
    received = []
    window.dismissed.connect(lambda: received.append(1))
    window.show()

    window._finish_dismiss()

    assert window.isVisible() is False
    assert received == [1]


def test_reset_state_hides_glyph_and_clears_answer(window: OverlayWindow) -> None:
    window.start_thinking()
    window.append_answer_token("some text")

    window._reset_state()

    assert window._answer_buffer == ""
    assert window._glyph.isHidden()
