from __future__ import annotations

import pytest
from pynput.keyboard import HotKey, Key, KeyCode
from pytest_mock import MockerFixture

from core.exceptions import HotkeyError
from ui.hotkey import DEBOUNCE_SECONDS, KEY_DOWN_FLAG, HotkeyListener, _combo_actually_held, _vk_of


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


def test_vk_of_resolves_a_key_enum_member() -> None:
    assert _vk_of(Key.ctrl) == Key.ctrl.value.vk


def test_vk_of_resolves_a_keycode_built_from_a_virtual_key_code() -> None:
    assert _vk_of(KeyCode.from_vk(32)) == 32


def test_vk_of_resolves_a_keycode_built_from_a_character(mocker: MockerFixture) -> None:
    mocker.patch("ui.hotkey.ctypes.windll.user32.VkKeyScanW", return_value=0x00BF)

    assert _vk_of(KeyCode.from_char("/")) == 0xBF


def test_combo_actually_held_is_true_when_every_key_is_down(mocker: MockerFixture) -> None:
    mocker.patch("ui.hotkey.ctypes.windll.user32.GetAsyncKeyState", return_value=KEY_DOWN_FLAG)

    assert _combo_actually_held([0x11, 32]) is True


def test_combo_actually_held_is_false_when_one_key_is_not_down(mocker: MockerFixture) -> None:
    mocker.patch(
        "ui.hotkey.ctypes.windll.user32.GetAsyncKeyState", side_effect=lambda vk: 0 if vk == 0x11 else KEY_DOWN_FLAG
    )

    assert _combo_actually_held([0x11, 32]) is False


def test_start_computes_the_combo_vks_for_the_configured_hotkey(mocker: MockerFixture) -> None:
    mocker.patch("ui.hotkey.keyboard.GlobalHotKeys")
    listener = HotkeyListener("<ctrl>+<space>")

    listener.start()

    assert listener._combo_vks == [Key.ctrl.value.vk, 32]


def test_activate_ignores_a_stale_activation_when_the_combo_is_not_actually_held(mocker: MockerFixture) -> None:
    mocker.patch("ui.hotkey.ctypes.windll.user32.GetAsyncKeyState", return_value=0)
    listener = HotkeyListener("<ctrl>+<space>")
    listener._combo_vks = [0x11, 32]
    received = []
    listener.summoned.connect(lambda: received.append(1))

    listener._on_activate()

    assert received == []


def test_activate_fires_when_the_combo_is_actually_held(mocker: MockerFixture) -> None:
    mocker.patch("ui.hotkey.ctypes.windll.user32.GetAsyncKeyState", return_value=KEY_DOWN_FLAG)
    listener = HotkeyListener("<ctrl>+<space>")
    listener._combo_vks = [0x11, 32]
    received = []
    listener.summoned.connect(lambda: received.append(1))

    listener._on_activate()

    assert received == [1]


def test_a_missed_ctrl_release_does_not_let_a_later_space_only_press_summon(mocker: MockerFixture) -> None:
    """Reproduces the real bug end-to-end: pynput's own HotKey can get ctrl stuck in its
    internal state after a missed release (which happens here because a successful
    activation immediately steals keyboard focus for the overlay), so a bare space press
    later re-matches the combo and calls _on_activate — which must refuse to fire since
    ctrl isn't actually held anymore."""
    listener = HotkeyListener("<ctrl>+<space>")
    listener._combo_vks = [Key.ctrl.value.vk, 32]
    received = []
    listener.summoned.connect(lambda: received.append(1))
    get_async_key_state = mocker.patch("ui.hotkey.ctypes.windll.user32.GetAsyncKeyState")
    clock = mocker.patch("ui.hotkey.time.monotonic")

    hotkey = HotKey(HotKey.parse("<ctrl>+<space>"), listener._on_activate)
    space_key = next(k for k in hotkey._keys if k != Key.ctrl)

    clock.return_value = 100.0
    get_async_key_state.return_value = KEY_DOWN_FLAG
    hotkey.press(Key.ctrl)
    hotkey.press(space_key)
    hotkey.release(space_key)
    # ctrl's own release event is missed here — pynput's _state still thinks it's held

    clock.return_value = 100.0 + DEBOUNCE_SECONDS + 0.01
    get_async_key_state.return_value = 0  # ctrl genuinely isn't held anymore
    hotkey.press(space_key)

    assert received == [1]
