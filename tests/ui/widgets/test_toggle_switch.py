from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QAbstractAnimation, QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

from ui.theme.tokens import GI_ORANGE
from ui.widgets.toggle_switch import TRACK_HEIGHT, TRACK_WIDTH, ToggleSwitch


@pytest.fixture
def switch() -> Iterator[ToggleSwitch]:
    widget = ToggleSwitch()
    widget.resize(widget.sizeHint())
    yield widget
    widget._slide.stop()


def _click(switch: ToggleSwitch) -> None:
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)


def test_toggle_switch_starts_off_and_checkable(switch: ToggleSwitch) -> None:
    assert (switch.isCheckable(), switch.isChecked(), switch.knob_position) == (True, False, 0.0)


def test_size_hint_is_the_track_size(switch: ToggleSwitch) -> None:
    assert switch.sizeHint() == QSize(TRACK_WIDTH, TRACK_HEIGHT)


def test_set_checked_jumps_the_knob_to_the_end(switch: ToggleSwitch) -> None:
    switch.setChecked(True)

    assert switch.knob_position == 1.0


def test_set_checked_does_not_animate(switch: ToggleSwitch) -> None:
    switch.setChecked(True)

    assert switch._slide.state() == QAbstractAnimation.State.Stopped


def test_set_checked_false_jumps_the_knob_back(switch: ToggleSwitch) -> None:
    switch.setChecked(True)

    switch.setChecked(False)

    assert switch.knob_position == 0.0


def test_click_toggles_the_switch(switch: ToggleSwitch) -> None:
    _click(switch)

    assert switch.isChecked()


def test_click_animates_the_knob_towards_on(switch: ToggleSwitch) -> None:
    _click(switch)

    assert (switch._slide.state(), switch._slide.endValue()) == (QAbstractAnimation.State.Running, 1.0)


def test_click_when_on_animates_the_knob_towards_off(switch: ToggleSwitch) -> None:
    switch.setChecked(True)

    _click(switch)

    assert (switch.isChecked(), switch._slide.startValue(), switch._slide.endValue()) == (False, 1.0, 0.0)


def test_click_emits_toggled(switch: ToggleSwitch) -> None:
    received: list[bool] = []
    switch.toggled.connect(received.append)

    _click(switch)

    assert received == [True]


def test_set_checked_emits_toggled(switch: ToggleSwitch) -> None:
    received: list[bool] = []
    switch.toggled.connect(received.append)

    switch.setChecked(True)

    assert received == [True]


def test_paint_event_fills_the_track_orange_when_on(switch: ToggleSwitch) -> None:
    switch.setChecked(True)

    image = switch.grab().toImage()

    assert image.pixelColor(6, TRACK_HEIGHT // 2).name() == QColor(GI_ORANGE).name()


def test_paint_event_dims_a_disabled_switch(switch: ToggleSwitch) -> None:
    switch.setChecked(True)
    enabled = switch.grab().toImage().pixelColor(6, TRACK_HEIGHT // 2)

    switch.setEnabled(False)

    assert switch.grab().toImage().pixelColor(6, TRACK_HEIGHT // 2) != enabled
