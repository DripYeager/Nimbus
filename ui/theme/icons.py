"""
Renders the Nimbus icon — the golden cloud — at any size, for the window, the tray and the
packaged executable. Owns icon rendering and export only; the cloud's shape lives in painting.py.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap

from ui.theme.painting import paint_cloud

ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def render_icon(size: int, with_tail: bool = True) -> QPixmap:
    """The cloud on a transparent square, padded so it reads well even at 16px."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    pad = size * 0.04
    height = size * 0.62
    paint_cloud(painter, QRectF(pad, (size - height) / 2, size - 2 * pad, height), with_tail)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """A multi-resolution icon — Windows picks the right size for the tray, taskbar and title bar."""
    icon = QIcon()
    for size in ICON_SIZES:
        # The tail turns to mush below 32px, so small sizes use the plain cloud.
        icon.addPixmap(render_icon(size, with_tail=size >= 32))
    return icon


def export_icon_files(directory: Path) -> tuple[Path, Path]:
    """Writes nimbus.png (256px) and a multi-size nimbus.ico for packaging."""
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    png_path, ico_path = directory / "nimbus.png", directory / "nimbus.ico"
    render_icon(256).save(str(png_path), "PNG")
    with Image.open(png_path) as image:
        image.save(ico_path, sizes=[(s, s) for s in ICON_SIZES])
    return png_path, ico_path
