"""
Registers the fonts bundled in assets/fonts and hands out the app's display, body and mono
faces. Owns font loading only; sizes and where each face is used are the widgets' business.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QWidget

from config.paths import asset_path
from core.logger import get_logger
from ui.theme.tokens import DISPLAY_FONT_FAMILY, FONT_FALLBACK, FONT_FAMILY, MONO_FONT_FAMILY

logger = get_logger(__name__)

BUNDLED_FONTS = ("Bangers-Regular.ttf",)


def load_bundled_fonts() -> None:
    """Makes the bundled faces available to Qt; call once after the QApplication exists."""
    for name in BUNDLED_FONTS:
        if QFontDatabase.addApplicationFont(str(asset_path("fonts", name))) < 0:
            logger.warning("Couldn't load a bundled font; falling back to the system face", extra={"font": name})


def display_font(pixel_size: int) -> QFont:
    """The comic-style headline face, with a heavy system face as the fallback."""
    font = QFont(DISPLAY_FONT_FAMILY)
    font.setFamilies([DISPLAY_FONT_FAMILY, "Segoe UI Black"])
    font.setPixelSize(pixel_size)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
    return font


def body_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The reading face (Segoe UI on Windows)."""
    font = QFont(FONT_FAMILY)
    font.setFamilies([FONT_FAMILY, FONT_FALLBACK])
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def mono_font(pixel_size: int) -> QFont:
    """The readout face for the power-level display and code."""
    font = QFont(MONO_FONT_FAMILY)
    font.setFamilies([MONO_FONT_FAMILY, "Consolas"])
    font.setPixelSize(pixel_size)
    return font


def use_display_font(widget: QWidget, pixel_size: int) -> None:
    """Gives widget the headline face. The app stylesheet sets a font family on every widget,
    which would override a plain setFont(); the "display" property opts the widget into the
    stylesheet's display-face rule instead, while setFont() still supplies the size."""
    widget.setProperty("display", "true")
    widget.setFont(display_font(pixel_size))
