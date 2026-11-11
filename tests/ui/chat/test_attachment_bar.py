from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton, QToolButton

from models.chat import Attachment
from ui.chat.attachment_bar import (
    FILE_SUGGESTIONS,
    SCREENSHOT_SUGGESTIONS,
    TEXT_SUGGESTIONS,
    AttachmentBar,
    describe_offer,
    suggestions_for,
)

REPORT = Attachment(name="report.pdf", path="C:/report.pdf")


@pytest.fixture
def bar(qapp: object) -> AttachmentBar:
    return AttachmentBar()


def _chips(bar: AttachmentBar) -> list[str]:
    return [b.text() for b in bar.findChildren(QPushButton)]


def _button(bar: AttachmentBar, text: str) -> QPushButton:
    return next(b for b in bar.findChildren(QPushButton) if b.text() == text)


@pytest.mark.parametrize(
    ("attachment", "expected"),
    [
        (REPORT, FILE_SUGGESTIONS),
        (Attachment(name="Copied text", text="hello"), TEXT_SUGGESTIONS),
        (Attachment(name="Screenshot", path="C:/shot.png"), SCREENSHOT_SUGGESTIONS),
    ],
)
def test_suggestions_for_fits_what_was_attached(attachment: Attachment, expected: tuple[str, ...]) -> None:
    assert suggestions_for(attachment) == expected


def test_describe_offer_counts_characters() -> None:
    assert describe_offer(1243) == "Use what I copied (1,243 characters)"


def test_init_starts_hidden(bar: AttachmentBar) -> None:
    assert bar.isHidden()


def test_offer_clipboard_shows_the_offer(bar: AttachmentBar) -> None:
    bar.offer_clipboard(50)

    assert (bar.isHidden(), bar.is_offering(), _chips(bar)) == (False, True, [describe_offer(50)])


def test_offer_clipboard_accept_emits_offer_accepted(bar: AttachmentBar) -> None:
    accepted: list[None] = []
    bar.offer_accepted.connect(lambda: accepted.append(None))
    bar.offer_clipboard(50)

    _button(bar, describe_offer(50)).click()

    assert accepted == [None]


def test_offer_clipboard_does_not_replace_an_attachment(bar: AttachmentBar) -> None:
    bar.show_attachment(REPORT)

    bar.offer_clipboard(50)

    assert not bar.is_offering()


def test_show_attachment_lists_the_name_and_suggestions(bar: AttachmentBar) -> None:
    bar.show_attachment(REPORT)

    assert _chips(bar) == ["report.pdf", *FILE_SUGGESTIONS]


def test_show_attachment_suggestion_click_emits_its_text(bar: AttachmentBar) -> None:
    asked: list[str] = []
    bar.suggestion_clicked.connect(asked.append)
    bar.show_attachment(REPORT)

    _button(bar, FILE_SUGGESTIONS[0]).click()

    assert asked == [FILE_SUGGESTIONS[0]]


def test_show_attachment_remove_button_emits_removed(bar: AttachmentBar) -> None:
    removed: list[None] = []
    bar.removed.connect(lambda: removed.append(None))
    bar.show_attachment(REPORT)

    next(b for b in bar.findChildren(QToolButton) if b.toolTip() == "Remove").click()

    assert removed == [None]


def test_show_attachment_none_hides_the_bar(bar: AttachmentBar) -> None:
    bar.show_attachment(REPORT)

    bar.show_attachment(None)

    assert bar.isHidden()
