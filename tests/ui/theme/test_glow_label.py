from __future__ import annotations

from PyQt6.QtGui import QColor

from ui.theme.glow_label import HALO_MARGIN_PX, GlowLabel


def test_init_keeps_the_text_and_glow_color(qapp: object) -> None:
    label = GlowLabel("NIMBUS", QColor(255, 120, 20, 45))

    assert (label.text(), label.glow_color().alpha()) == ("NIMBUS", 45)


def test_init_leaves_room_for_the_halo(qapp: object) -> None:
    label = GlowLabel("NIMBUS", QColor("orange"))

    assert label.contentsMargins().left() == HALO_MARGIN_PX


def test_paint_draws_without_a_graphics_effect(qapp: object) -> None:
    label = GlowLabel("WHERE TO?", QColor("orange"))
    label.resize(200, 60)

    image = label.grab().toImage()

    assert (label.graphicsEffect(), image.isNull()) == (None, False)
