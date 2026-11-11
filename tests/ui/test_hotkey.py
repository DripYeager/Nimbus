from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from core.exceptions import HotkeyError
from ui.hotkey import DEBOUNCE_SECONDS, HOTKEY_ID, MOD_NOREPEAT, WM_HOTKEY, WM_QUIT, HotkeyListener, parse_hotkey

CTRL, ALT, SHIFT, WIN = 0x0002, 0x0001, 0x0004, 0x0008


def _wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Pumps Qt events until condition holds, summoned crosses threads as a queued signal."""
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return condition()


@pytest.mark.parametrize(
    ("hotkey", "expected"),
    [
        ("<ctrl>+<space>", (CTRL, 0x20)),
        ("<ctrl>+<shift>+n", (CTRL | SHIFT, ord("N"))),
        ("<alt>+7", (ALT, ord("7"))),
        ("<win>+<tab>", (WIN, 0x09)),
        ("<cmd>+<enter>", (WIN, 0x0D)),
        ("<ctrl>+<f1>", (CTRL, 0x70)),
        ("<alt>+<f24>", (ALT, 0x70 + 23)),
        (" <CTRL> + <Alt> + K ", (CTRL | ALT, ord("K"))),
    ],
)
def test_parse_hotkey_returns_modifiers_and_virtual_key(hotkey: str, expected: tuple[int, int]) -> None:
    assert parse_hotkey(hotkey) == expected


@pytest.mark.parametrize(
    "hotkey",
    ["", "n", "<ctrl>", "<ctrl>+", "<ctrl>+a+b", "<ctrl>+<f0>", "<ctrl>+<f25>", "<ctrl>+<hyper>", "<ctrl>+ab"],
)
def test_parse_hotkey_raises_on_invalid_combo(hotkey: str) -> None:
    with pytest.raises(HotkeyError):
        parse_hotkey(hotkey)


def test_parse_hotkey_asks_windows_for_punctuation_keys(mocker: MockerFixture) -> None:
    mocker.patch.object(ctypes.windll.user32, "VkKeyScanW", return_value=0x01BA)

    assert parse_hotkey("<ctrl>+;") == (CTRL, 0xBA)


def test_parse_hotkey_raises_when_the_layout_cannot_type_the_key(mocker: MockerFixture) -> None:
    mocker.patch.object(ctypes.windll.user32, "VkKeyScanW", return_value=0xFFFF)

    with pytest.raises(HotkeyError):
        parse_hotkey("<ctrl>+§")


def test_parse_hotkey_does_not_treat_non_ascii_letters_as_virtual_keys(mocker: MockerFixture) -> None:
    scan = mocker.patch.object(ctypes.windll.user32, "VkKeyScanW", return_value=0x00DE)

    assert parse_hotkey("<ctrl>+é") == (CTRL, 0xDE)
    scan.assert_called_once_with(ord("é"))


class FakeUser32:
    """Stands in for the Win32 calls the listener makes; GetMessageW blocks until WM_QUIT is posted."""

    def __init__(self, register_result: int = 1, pending_hotkeys: int = 0) -> None:
        self.register_result = register_result
        self.pending_hotkeys = pending_hotkeys
        self.quit = threading.Event()
        self.RegisterHotKey = Mock(side_effect=lambda *_: self.register_result)
        self.UnregisterHotKey = Mock(return_value=1)
        self.PostThreadMessageW = Mock(side_effect=self._post)
        self.GetMessageW = Mock(side_effect=self._get_message)

    def _post(self, thread_id: int, message: int, *_: Any) -> int:
        if message == WM_QUIT:
            self.quit.set()
        return 1

    def _get_message(self, message_ref: Any, *_: Any) -> int:
        if self.pending_hotkeys:
            self.pending_hotkeys -= 1
            message_ref._obj.message = WM_HOTKEY
            return 1
        self.quit.wait(5)
        return 0


@pytest.fixture
def user32(mocker: MockerFixture) -> FakeUser32:
    fake = FakeUser32()
    for name in ("RegisterHotKey", "UnregisterHotKey", "PostThreadMessageW", "GetMessageW"):
        mocker.patch.object(ctypes.windll.user32, name, getattr(fake, name))
    return fake


@pytest.fixture
def listener() -> Iterator[HotkeyListener]:
    hotkey_listener = HotkeyListener("<ctrl>+<space>")
    yield hotkey_listener
    hotkey_listener.stop()


def test_hotkey_listener_start_registers_with_windows(user32: FakeUser32, listener: HotkeyListener) -> None:
    listener.start()

    user32.RegisterHotKey.assert_called_once_with(None, HOTKEY_ID, CTRL | MOD_NOREPEAT, 0x20)


def test_hotkey_listener_start_raises_when_the_hotkey_is_taken(user32: FakeUser32, listener: HotkeyListener) -> None:
    user32.register_result = 0

    with pytest.raises(HotkeyError, match="already used by another app"):
        listener.start()


def test_hotkey_listener_start_raises_for_an_invalid_hotkey(user32: FakeUser32) -> None:
    with pytest.raises(HotkeyError):
        HotkeyListener("<ctrl>").start()
    user32.RegisterHotKey.assert_not_called()


def test_hotkey_listener_start_raises_off_windows(mocker: MockerFixture, user32: FakeUser32) -> None:
    mocker.patch("ui.hotkey.sys.platform", "linux")

    with pytest.raises(HotkeyError, match="only supported on Windows"):
        HotkeyListener("<ctrl>+<space>").start()


def test_hotkey_listener_start_raises_when_registration_times_out(mocker: MockerFixture, user32: FakeUser32) -> None:
    mocker.patch("ui.hotkey.REGISTER_WAIT_SECONDS", 0.05)
    release = threading.Event()
    user32.RegisterHotKey.side_effect = lambda *_: 0 if release.wait(5) else 0
    hotkey_listener = HotkeyListener("<ctrl>+<space>")

    with pytest.raises(HotkeyError, match="Timed out"):
        hotkey_listener.start()
    release.set()


def test_hotkey_listener_stop_posts_quit_and_unregisters(user32: FakeUser32, listener: HotkeyListener) -> None:
    listener.start()
    thread = listener._thread

    listener.stop()

    assert not thread.is_alive()
    user32.UnregisterHotKey.assert_called_once_with(None, HOTKEY_ID)


def test_hotkey_listener_stop_is_safe_before_start(user32: FakeUser32) -> None:
    HotkeyListener("<ctrl>+<space>").stop()

    user32.PostThreadMessageW.assert_not_called()


def test_hotkey_listener_emits_summoned_on_wm_hotkey(user32: FakeUser32, listener: HotkeyListener) -> None:
    user32.pending_hotkeys = 1
    fired = threading.Event()
    listener.summoned.connect(fired.set)

    listener.start()

    assert _wait_for(fired.is_set)


def test_hotkey_listener_rebind_switches_to_the_new_hotkey(user32: FakeUser32, listener: HotkeyListener) -> None:
    listener.start()

    listener.rebind("<alt>+n")

    assert listener.hotkey == "<alt>+n"
    user32.RegisterHotKey.assert_called_with(None, HOTKEY_ID, ALT | MOD_NOREPEAT, ord("N"))


def test_hotkey_listener_rebind_restores_the_old_hotkey_on_failure(
    user32: FakeUser32, listener: HotkeyListener
) -> None:
    listener.start()
    user32.RegisterHotKey.side_effect = lambda _hwnd, _id, _mods, vk: 0 if vk == ord("N") else 1

    with pytest.raises(HotkeyError, match="<alt>\\+n"):
        listener.rebind("<alt>+n")
    assert listener.hotkey == "<ctrl>+<space>"
    assert listener._thread is not None


def test_hotkey_listener_rebind_reports_the_new_hotkey_when_restore_also_fails(
    user32: FakeUser32, listener: HotkeyListener
) -> None:
    listener.start()
    user32.register_result = 0

    with pytest.raises(HotkeyError, match="<alt>\\+n"):
        listener.rebind("<alt>+n")


def test_fire_emits_summoned_once_within_the_debounce_window(mocker: MockerFixture) -> None:
    clock = mocker.patch("ui.hotkey.time")
    hotkey_listener = HotkeyListener("<ctrl>+<space>")
    presses: list[None] = []
    hotkey_listener.summoned.connect(lambda: presses.append(None))

    for now in (100.0, 100.0 + DEBOUNCE_SECONDS / 2):
        clock.monotonic.return_value = now
        hotkey_listener._fire()

    assert len(presses) == 1


def test_fire_emits_again_after_the_debounce_window(mocker: MockerFixture) -> None:
    clock = mocker.patch("ui.hotkey.time")
    hotkey_listener = HotkeyListener("<ctrl>+<space>")
    presses: list[None] = []
    hotkey_listener.summoned.connect(lambda: presses.append(None))

    for now in (100.0, 100.0 + DEBOUNCE_SECONDS):
        clock.monotonic.return_value = now
        hotkey_listener._fire()

    assert len(presses) == 2
