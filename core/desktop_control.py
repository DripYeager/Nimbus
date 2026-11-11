"""
Small desktop actions the assistant can take: put text on the clipboard, press the media and
volume keys, and list, switch to or close app windows. Everything goes through ordinary
Windows APIs (pywin32) with the user's normal rights; closing a window asks the app to close,
exactly like clicking its X, so unsaved work still gets the app's own "save?" prompt. Owns
these OS calls only; when they may run is the tools' business.
"""

from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass

import psutil
import pywintypes
import win32api
import win32clipboard
import win32con
import win32gui
import win32process

from core.exceptions import ToolError

CLIPBOARD_ATTEMPTS = 10
CLIPBOARD_RETRY_S = 0.05
# Each press of a volume key moves Windows' volume by 2%.
VOLUME_STEP_PERCENT = 2
# A full sweep from mute to full. More presses than this only holds the assistant up.
MAX_KEY_PRESSES = 100 // VOLUME_STEP_PERCENT
KEY_PRESS_GAP_S = 0.01
# Windows' virtual-key codes for the media keys (win32con doesn't define them).
MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "mute": 0xAD,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
}

DWMWA_CLOAKED = 14

_last_copied = ""


@dataclass(frozen=True)
class AppWindow:
    handle: int
    title: str
    program: str


def copy_text(text: str) -> None:
    """Puts text on the clipboard, retrying while another app briefly holds it."""
    global _last_copied
    for _ in range(CLIPBOARD_ATTEMPTS):
        try:
            win32clipboard.OpenClipboard()
        except pywintypes.error:
            time.sleep(CLIPBOARD_RETRY_S)
            continue
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
        _last_copied = text
        return
    raise ToolError("Another app is holding the clipboard. Try again in a moment.")


def was_copied_by_nimbus(text: str) -> bool:
    """True for text Nimbus itself put on the clipboard, so it isn't offered back as 'copied'."""
    return bool(text) and text.strip() == _last_copied.strip()


def press_media_key(action: str, times: int = 1) -> None:
    """Presses a media or volume key, the same as the keyboard's own keys."""
    key = MEDIA_KEYS.get(action)
    if key is None:
        raise ToolError(f"Unknown media action {action!r}. Use one of: {', '.join(MEDIA_KEYS)}.")
    for _ in range(min(MAX_KEY_PRESSES, max(1, times))):
        win32api.keybd_event(key, 0, 0, 0)
        win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(KEY_PRESS_GAP_S)


def set_volume(percent: int) -> int:
    """Sets the volume to about percent (in 2% steps) by going to zero and stepping up.
    Returns the volume it set."""
    percent = max(0, min(100, int(percent)))
    press_media_key("volume_down", 100 // VOLUME_STEP_PERCENT)
    steps = round(percent / VOLUME_STEP_PERCENT)
    if steps:
        press_media_key("volume_up", steps)
    return steps * VOLUME_STEP_PERCENT


def open_windows() -> list[AppWindow]:
    """The app windows a person would see in Alt+Tab, Nimbus's own excluded."""
    windows: list[AppWindow] = []
    win32gui.EnumWindows(lambda handle, _: _collect(handle, windows), None)
    return windows


def find_window(query: str) -> AppWindow:
    """The window whose program or title best matches query ("excel", "spotify", "budget.xlsx").

    Raises:
        ToolError: Nothing open matches.
    """
    wanted = query.strip().lower().removesuffix(".exe")
    windows = open_windows()
    for matches in (
        lambda w: w.program.lower() == wanted,
        lambda w: wanted in w.program.lower(),
        lambda w: wanted in w.title.lower(),
    ):
        found = [window for window in windows if matches(window)]
        if found:
            return found[0]
    names = ", ".join(sorted({w.program for w in windows})) or "none"
    raise ToolError(f"No open window matches {query!r}. Open programs: {names}.")


def switch_to(window: AppWindow) -> None:
    """Brings window to the front, restoring it if it's minimized."""
    try:
        if win32gui.IsIconic(window.handle):
            win32gui.ShowWindow(window.handle, win32con.SW_RESTORE)
        # Windows only lets the app the user last used change the foreground; a tap of Alt
        # counts as that, so the switch isn't silently ignored.
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(window.handle)
    except pywintypes.error as e:
        raise ToolError(f"Couldn't switch to {window.title}: {e.strerror}") from e


def close(window: AppWindow) -> None:
    """Asks the window to close, like clicking its X."""
    try:
        win32gui.PostMessage(window.handle, win32con.WM_CLOSE, 0, 0)
    except pywintypes.error as e:
        raise ToolError(f"Couldn't close {window.title}: {e.strerror}") from e


def _collect(handle: int, windows: list[AppWindow]) -> bool:
    if _is_app_window(handle):
        _, pid = win32process.GetWindowThreadProcessId(handle)
        if pid != os.getpid():
            windows.append(AppWindow(handle, win32gui.GetWindowText(handle), _program(pid)))
    return True


def _is_app_window(handle: int) -> bool:
    """Visible, titled, top-level and not a tool palette: what Alt+Tab would show."""
    if not win32gui.IsWindowVisible(handle) or not win32gui.GetWindowText(handle).strip():
        return False
    if win32gui.GetWindow(handle, win32con.GW_OWNER):
        return False
    style = win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
    return not style & win32con.WS_EX_TOOLWINDOW and not _is_cloaked(handle)


def _is_cloaked(handle: int) -> bool:
    """Store apps keep hidden frames around ("cloaked"); Alt+Tab skips them, and so do we."""
    cloaked = ctypes.c_int(0)
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(handle), DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    return result == 0 and bool(cloaked.value)


def _program(pid: int) -> str:
    try:
        return psutil.Process(pid).name().removesuffix(".exe")
    except psutil.Error:
        return "unknown"
