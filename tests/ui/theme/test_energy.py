from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QAbstractAnimation, QPointF
from PyQt6.QtGui import QColor

from ui.theme.energy import ORB_REST_GLOW, EnergyOrb, PowerLevelReadout, _radial
from ui.theme.tokens import SCOUTER_GREEN

ORB_SIZE = 34


@pytest.fixture
def orb() -> Iterator[EnergyOrb]:
    widget = EnergyOrb(ORB_SIZE)
    yield widget
    widget.stop()


@pytest.fixture
def readout() -> PowerLevelReadout:
    widget = PowerLevelReadout()
    widget.resize(200, 28)
    return widget


def test_energy_orb_has_the_requested_fixed_size(orb: EnergyOrb) -> None:
    assert (orb.minimumSize(), orb.maximumSize()) == (orb.size(), orb.size())


def test_energy_orb_starts_at_rest(orb: EnergyOrb) -> None:
    assert (orb.glow, orb._pulse.state()) == (ORB_REST_GLOW, QAbstractAnimation.State.Stopped)


def test_start_pulses_the_orb(orb: EnergyOrb) -> None:
    orb.start()

    assert orb._pulse.state() == QAbstractAnimation.State.Running


def test_stop_returns_the_orb_to_rest(orb: EnergyOrb) -> None:
    orb.start()
    orb.glow = 0.9

    orb.stop()

    assert (orb.glow, orb._pulse.state()) == (ORB_REST_GLOW, QAbstractAnimation.State.Stopped)


def test_glow_property_is_animatable(orb: EnergyOrb) -> None:
    orb.setProperty("glow", 0.7)

    assert orb.glow == pytest.approx(0.7)


def test_energy_orb_paints_a_bright_core(orb: EnergyOrb) -> None:
    image = orb.grab().toImage()

    assert image.pixelColor(ORB_SIZE // 2, ORB_SIZE // 2 + 4).alpha() == 255


def test_set_progress_stores_the_value(readout: PowerLevelReadout) -> None:
    readout.set_progress(1240, 0.5)

    assert (readout._value, readout._ratio) == (1240, 0.5)


@pytest.mark.parametrize(("ratio", "expected"), [(-0.5, 0.0), (1.7, 1.0)])
def test_set_progress_clamps_the_ratio(readout: PowerLevelReadout, ratio: float, expected: float) -> None:
    readout.set_progress(10, ratio)

    assert readout._ratio == expected


def test_paint_event_fills_the_scan_bar_to_the_ratio(readout: PowerLevelReadout) -> None:
    readout.set_progress(10, 0.5)

    image = readout.grab().toImage()

    filled, empty = image.pixelColor(50, 22), image.pixelColor(150, 22)
    assert filled.green() > empty.green()


def test_paint_event_draws_in_scouter_green(readout: PowerLevelReadout) -> None:
    readout.set_progress(10, 1.0)

    assert readout.grab().toImage().pixelColor(100, 22).name() == QColor(SCOUTER_GREEN).name()


def test_radial_applies_each_stop_alpha() -> None:
    gradient = _radial(QPointF(0, 0), 10, [(0.0, "#FF0000", 0.5), (1.0, "#FF0000", 0.0)])

    assert [round(color.alphaF(), 2) for _, color in gradient.stops()] == [0.5, 0.0]
