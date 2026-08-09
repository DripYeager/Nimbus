from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from core.exceptions import HotkeyError
from ui.hotkey import DEBOUNCE_SECONDS, HotkeyListener


@pytest.fixture(autouse=True, scope="session")
def _qapp():
    """QObject/pyqtSignal machinery needs a QApplication instance to exist somewhere."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_start_registers_the_configured_hotkey(mocker: MockerFixture) -> None:
    global_hotkeys_cls = mocker.patch("ui.hotkey.keyboard.GlobalHotKeys")
    listener = HotkeyListener("<ctrl>+<space>")

    listener.start()

    args, kwargs = global_hotkeys_cls.call_args
    registered = args[0] if args else kwargs["hotkeys"]
    assert list(registered.keys()) == ["<ctrl>+<space>"]
    global_hotkeys_cls.return_value.start.assert_called_once()


def test_start_raises_hotkey_error_for_an_invalid_hotkey_string() -> None:
    with pytest.raises(HotkeyError):
        HotkeyListener("this is not a valid hotkey").start()


def test_stop_is_safe_when_never_started() -> None:
    HotkeyListener("<ctrl>+<space>").stop()


def test_stop_stops_the_underlying_listener(mocker: MockerFixture) -> None:
    global_hotkeys_cls = mocker.patch("ui.hotkey.keyboard.GlobalHotKeys")
    listener = HotkeyListener("<ctrl>+<space>")
    listener.start()

    listener.stop()

    global_hotkeys_cls.return_value.stop.assert_called_once()
    global_hotkeys_cls.return_value.join.assert_called_once()


def test_activate_emits_summoned(mocker: MockerFixture) -> None:
    listener = HotkeyListener("<ctrl>+<space>")
    received = []
    listener.summoned.connect(lambda: received.append(1))

    listener._on_activate()

    assert received == [1]


def test_activate_is_debounced_against_a_rapid_retrigger(mocker: MockerFixture) -> None:
    listener = HotkeyListener("<ctrl>+<space>")
    received = []
    listener.summoned.connect(lambda: received.append(1))

    listener._on_activate()
    listener._on_activate()

    assert received == [1]


def test_activate_fires_again_once_the_debounce_window_has_passed(mocker: MockerFixture) -> None:
    listener = HotkeyListener("<ctrl>+<space>")
    received = []
    listener.summoned.connect(lambda: received.append(1))
    clock = mocker.patch("ui.hotkey.time.monotonic")

    clock.return_value = 100.0
    listener._on_activate()
    clock.return_value = 100.0 + DEBOUNCE_SECONDS + 0.01
    listener._on_activate()

    assert received == [1, 1]
