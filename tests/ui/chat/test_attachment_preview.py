from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QWidget
from pytest_mock import MockerFixture

from core.attachment_format import AttachedItem
from models.chat import Attachment
from ui.chat.attachment_bar import AttachmentBar
from ui.chat.attachment_preview import ImagePreview, image_preview, is_image, thumbnail
from ui.chat.user_bubble import UserBubble


@pytest.fixture
def shot(tmp_path: Path, qapp: object) -> Path:
    path = tmp_path / "screenshot.png"
    image = QPixmap(800, 400)
    image.fill(QColor("white"))
    image.save(str(path))
    return path


@pytest.mark.parametrize(("path", "expected"), [("a.PNG", True), ("a.jpg", True), ("a.pdf", False), (None, False)])
def test_is_image_by_extension(path: str | None, expected: bool) -> None:
    assert is_image(path) is expected


def test_thumbnail_fits_within_the_box_keeping_its_shape(shot: Path) -> None:
    picture = thumbnail(str(shot), 200, 200)

    assert picture is not None
    assert (picture.width(), picture.height()) == (200, 100)


def test_thumbnail_is_none_for_a_missing_file(tmp_path: Path, qapp: object) -> None:
    assert thumbnail(str(tmp_path / "gone.png"), 100, 100) is None


def test_image_preview_is_none_for_non_images(qapp: object) -> None:
    assert image_preview("C:/Docs/report.pdf", 100, 100, QWidget()) is None


def test_image_preview_click_opens_the_full_image(shot: Path, mocker: MockerFixture) -> None:
    opener = mocker.patch("ui.chat.attachment_preview.open_source")
    preview = image_preview(str(shot), 100, 100, QWidget())
    assert preview is not None

    preview.mouseReleaseEvent(mocker.Mock(button=mocker.Mock(return_value=preview_left_button())))

    opener.assert_called_once_with(str(shot))


def preview_left_button() -> object:
    from PyQt6.QtCore import Qt

    return Qt.MouseButton.LeftButton


def test_user_bubble_shows_a_screenshot_as_a_picture(shot: Path) -> None:
    bubble = UserBubble("What does this say?", attachments=(AttachedItem("Screenshot", str(shot)),))

    assert [p.path() for p in bubble.findChildren(ImagePreview)] == [str(shot)]


def test_user_bubble_shows_no_picture_for_a_document(qapp: object) -> None:
    bubble = UserBubble("Summarize it", attachments=(AttachedItem("report.pdf", "C:/Docs/report.pdf"),))

    assert bubble.findChildren(ImagePreview) == []


def test_attachment_bar_previews_an_attached_screenshot(shot: Path) -> None:
    bar = AttachmentBar()

    bar.show_attachment(Attachment(name="Screenshot", path=str(shot)))

    assert len(bar.findChildren(ImagePreview)) == 1
