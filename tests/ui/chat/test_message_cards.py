from __future__ import annotations

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel, QPushButton
from pytest_mock import MockerFixture

from models.schema import SourceRef
from ui.chat.message_cards import STEP_ICON_SIZE, STEP_ICONS, ConfirmCard, SourceCard, ToolStep
from ui.theme.line_icons import line_pixmap


@pytest.fixture
def open_url(mocker: MockerFixture) -> Mock:
    """Clicking a source card must never open a real file in tests."""
    return mocker.patch("ui.source_opener.QDesktopServices.openUrl")


@pytest.fixture
def pixmaps(mocker: MockerFixture) -> Mock:
    """Records which icon each step asks for while still drawing the real one."""
    return mocker.patch("ui.chat.message_cards.line_pixmap", wraps=line_pixmap)


@pytest.fixture
def card() -> ConfirmCard:
    return ConfirmCard("Open Notepad")


@pytest.fixture
def decisions(card: ConfirmCard) -> list[tuple[bool, bool]]:
    received: list[tuple[bool, bool]] = []
    card.decided.connect(lambda approved, always: received.append((approved, always)))
    return received


def _button(card: ConfirmCard, text: str) -> QPushButton:
    return next(b for b in card.findChildren(QPushButton) if b.text() == text)


def _label_texts(widget: QPushButton | ConfirmCard) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel) if label.text()]


def test_update_step_shows_the_label_and_status() -> None:
    step = ToolStep()

    step.update_step("Searching files", "running")

    assert (step._text.text(), step._text.property("status")) == ("Searching files", "running")


@pytest.mark.parametrize("status", list(STEP_ICONS))
def test_update_step_draws_the_icon_for_its_status(pixmaps: Mock, status: str) -> None:
    step = ToolStep()

    step.update_step("Step", status)

    pixmaps.assert_called_once_with(*STEP_ICONS[status], STEP_ICON_SIZE)


def test_update_step_falls_back_to_the_info_icon_for_an_unknown_status(pixmaps: Mock) -> None:
    step = ToolStep()

    step.update_step("Step", "mystery")

    pixmaps.assert_called_once_with(*STEP_ICONS["info"], STEP_ICON_SIZE)


def test_source_card_shows_the_file_name_and_folder() -> None:
    card = SourceCard(SourceRef(file_name="cv.pdf", file_path="C:/Docs/Work/cv.pdf", score=0.9))

    assert _label_texts(card) == ["cv.pdf", "Work"]


def test_source_card_tooltip_names_the_file() -> None:
    card = SourceCard(SourceRef(file_name="cv.pdf", file_path="C:/Docs/cv.pdf", score=0.9))

    assert card.toolTip() == "Open C:/Docs/cv.pdf"


def test_source_card_click_opens_the_file(open_url: Mock) -> None:
    card = SourceCard(SourceRef(file_name="cv.pdf", file_path="C:/Docs/cv.pdf", score=0.9))

    card.click()

    open_url.assert_called_once_with(QUrl.fromLocalFile("C:/Docs/cv.pdf"))


def test_confirm_card_shows_the_description(card: ConfirmCard) -> None:
    assert "Open Notepad" in _label_texts(card)


@pytest.mark.parametrize(
    ("button_text", "expected"), [("Allow", (True, False)), ("Always allow", (True, True)), ("Don't", (False, False))]
)
def test_decide_reports_the_choice(
    card: ConfirmCard, decisions: list[tuple[bool, bool]], button_text: str, expected: tuple[bool, bool]
) -> None:
    _button(card, button_text).click()

    assert decisions == [expected]


def test_decide_locks_every_button(card: ConfirmCard, decisions: list[tuple[bool, bool]]) -> None:
    _button(card, "Allow").click()

    assert not any(b.isEnabled() for b in card.findChildren(QPushButton))


def test_decide_ignores_a_second_click(card: ConfirmCard, decisions: list[tuple[bool, bool]]) -> None:
    _button(card, "Allow").click()

    _button(card, "Don't").click()

    assert decisions == [(True, False)]


def test_confirm_card_reopen_unlocks_the_buttons(qapp: object) -> None:
    card = ConfirmCard("Open Notepad")
    card._decide(True, False)

    card.reopen()

    assert card.is_open() and all(b.isEnabled() for b in card.findChildren(QPushButton))


def test_source_card_shows_the_cited_page(qapp: object) -> None:
    card = SourceCard(SourceRef(file_name="cv.pdf", file_path="C:/Docs/cv.pdf", score=0.9, page=3))

    labels = [label.text() for label in card.findChildren(QLabel)]

    assert any(text.endswith("p. 3") for text in labels)


def test_source_card_click_opens_the_pdf_at_its_page(mocker: MockerFixture) -> None:
    opener = mocker.patch("ui.chat.message_cards.open_source")
    card = SourceCard(SourceRef(file_name="cv.pdf", file_path="C:/Docs/cv.pdf", score=0.9, page=3))

    card.click()

    opener.assert_called_once_with("C:/Docs/cv.pdf", 3)
