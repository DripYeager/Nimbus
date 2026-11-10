"""
Loads the Lucide line icons bundled in assets/icons (ISC licence) and tints them to any theme
colour. Owns SVG loading, recolouring and caching; which icon a widget shows is up to the widget.
"""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from config.paths import asset_path
from core.logger import get_logger

logger = get_logger(__name__)

# Rendered at 2x and scaled down so strokes stay crisp on high-DPI screens.
SUPERSAMPLE = 2
STROKE_WIDTH = "2"


@lru_cache(maxsize=256)
def line_pixmap(name: str, color: str, size: int, stroke_width: str = STROKE_WIDTH) -> QPixmap:
    """The named icon drawn in color at size×size device-independent pixels."""
    pixmap = QPixmap(size * SUPERSAMPLE, size * SUPERSAMPLE)
    pixmap.fill(Qt.GlobalColor.transparent)
    svg = _tinted_svg(name, color, stroke_width)
    if svg is None:
        return pixmap
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg)).render(painter, QRectF(0, 0, pixmap.width(), pixmap.height()))
    painter.end()
    pixmap.setDevicePixelRatio(SUPERSAMPLE)
    return pixmap


def line_icon(name: str, color: str, size: int = 18, hover_color: str | None = None) -> QIcon:
    """A QIcon for buttons; hover_color, if given, is shown while the button is hovered."""
    icon = QIcon(line_pixmap(name, color, size))
    if hover_color:
        icon.addPixmap(line_pixmap(name, hover_color, size), QIcon.Mode.Active)
    return icon


@lru_cache(maxsize=64)
def _tinted_svg(name: str, color: str, stroke_width: str) -> bytes | None:
    """The icon's SVG with currentColor and the stroke width replaced."""
    path = asset_path("icons", f"{name}.svg")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Missing icon", extra={"icon": name})
        return None
    text = text.replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
    return text.encode("utf-8")
