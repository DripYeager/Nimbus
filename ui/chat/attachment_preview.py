"""
Small previews of attached images, so a screenshot shows up as a picture rather than just its
name: in the attachment bar before sending, and in the user's message afterwards. Clicking a
preview opens the full image. Display only.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget

from ui.source_opener import open_source

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"})


def is_image(path: str | None) -> bool:
    return path is not None and Path(path).suffix.lower() in IMAGE_EXTENSIONS


def thumbnail(path: str, max_width: int, max_height: int) -> QPixmap | None:
    """The image scaled down to fit, or None if it can't be read (moved, deleted, broken)."""
    image = QPixmap(path)
    if image.isNull():
        return None
    if image.width() <= max_width and image.height() <= max_height:
        return image
    return image.scaled(
        max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class ImagePreview(QLabel):
    """A thumbnail that opens the full image when clicked."""

    def __init__(self, path: str, picture: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ImagePreview")
        self._path = path
        self.setPixmap(picture)
        self.setFixedSize(picture.size())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open the full image")

    def path(self) -> str:
        return self._path

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            open_source(self._path)


def image_preview(path: str | None, max_width: int, max_height: int, parent: QWidget) -> ImagePreview | None:
    """A clickable thumbnail for an attached image, or None for anything else."""
    if path is None or not is_image(path):
        return None
    picture = thumbnail(path, max_width, max_height)
    return ImagePreview(path, picture, parent) if picture is not None else None
