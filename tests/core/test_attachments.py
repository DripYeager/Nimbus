from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.attachment_format import AttachedItem, split_attachments
from core.attachments import MAX_ATTACHMENT_CHARS, NO_TEXT_NOTE, TRUNCATED_NOTE, attach
from core.exceptions import ParsingError
from models.chat import Attachment


def test_attach_reads_an_attached_file(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("The launch moved to May.", encoding="utf-8")

    message = attach("When is the launch?", Attachment(name="notes.txt", path=str(notes)))

    assert "The launch moved to May." in message
    assert split_attachments(message) == ("When is the launch?", [AttachedItem("notes.txt", str(notes))])


def test_attach_uses_attached_text_as_is() -> None:
    message = attach("Translate this", Attachment(name="Copied text", text="Bonjour"))

    assert "\nBonjour\n" in message


def test_attach_cuts_very_long_text() -> None:
    message = attach("Summarize", Attachment(name="Copied text", text="#" * (MAX_ATTACHMENT_CHARS + 50)))

    assert TRUNCATED_NOTE.strip() in message
    assert message.count("#") == MAX_ATTACHMENT_CHARS


def test_attach_says_when_there_is_no_text(mocker: MockerFixture, tmp_path: Path) -> None:
    image = tmp_path / "blank.png"
    image.write_bytes(b"png")
    mocker.patch("core.attachments.extract_text_from_image", return_value="  ")

    assert NO_TEXT_NOTE in attach("What is this?", Attachment(name="blank.png", path=str(image)))


def test_attach_raises_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ParsingError, match="Couldn't find"):
        attach("hi", Attachment(name="gone.pdf", path=str(tmp_path / "gone.pdf")))


def test_attach_reads_a_tiny_screenshot_instead_of_skipping_it_as_an_icon(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    ocr = mocker.patch("core.attachments.extract_text_from_image", return_value="Error 42")
    shot = tmp_path / "screenshot.png"
    shot.write_bytes(b"png")

    message = attach("What does this say?", Attachment(name="Screenshot", path=str(shot)))

    ocr.assert_called_once_with(shot, skip_icons=False)
    assert "Error 42" in message
