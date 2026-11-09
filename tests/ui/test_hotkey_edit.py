from __future__ import annotations

import pytest
from PyQt6.QtCore import QKeyCombination, Qt
from PyQt6.QtGui import QKeySequence

from ui.settings.hotkey_edit import HotkeyEdit, from_hotkey_string, to_hotkey_string

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier


def _chord(modifiers: Qt.KeyboardModifier, key: Qt.Key) -> QKeySequence:
    return QKeySequence(QKeyCombination(modifiers, key))


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        (_chord(CTRL, Qt.Key.Key_Space), "<ctrl>+<space>"),
        (_chord(CTRL | SHIFT, Qt.Key.Key_N), "<ctrl>+<shift>+n"),
        (_chord(ALT, Qt.Key.Key_F2), "<alt>+<f2>"),
        (_chord(Qt.KeyboardModifier.MetaModifier, Qt.Key.Key_7), "<win>+7"),
    ],
)
def test_to_hotkey_string_converts_supported_chords(sequence: QKeySequence, expected: str) -> None:
    assert to_hotkey_string(sequence) == expected


@pytest.mark.parametrize(
    "sequence",
    [
        QKeySequence(),
        _chord(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_A),
        _chord(CTRL, Qt.Key.Key_Escape),
        _chord(CTRL, Qt.Key.Key_F13),
    ],
)
def test_to_hotkey_string_rejects_unsupported_chords(sequence: QKeySequence) -> None:
    assert to_hotkey_string(sequence) == ""


@pytest.mark.parametrize("hotkey", ["<ctrl>+<space>", "<ctrl>+<shift>+n", "<alt>+<f12>", "<win>+0"])
def test_from_hotkey_string_round_trips(hotkey: str) -> None:
    assert to_hotkey_string(from_hotkey_string(hotkey)) == hotkey


@pytest.mark.parametrize("hotkey", ["", "n", "<ctrl>", "<ctrl>+<esc>", "<hyper>+n", "<ctrl>+<f13>"])
def test_from_hotkey_string_returns_empty_for_invalid(hotkey: str) -> None:
    assert from_hotkey_string(hotkey).isEmpty()


def test_hotkey_edit_set_hotkey_round_trips() -> None:
    edit = HotkeyEdit()
    edit.set_hotkey("<ctrl>+<alt>+k")
    assert edit.hotkey() == "<ctrl>+<alt>+k"


def test_hotkey_edit_shows_hint_for_unsupported_chord() -> None:
    edit = HotkeyEdit()
    edit._edit.setKeySequence(_chord(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_A))
    assert edit.hotkey() == ""
    assert not edit._hint.isHidden()


def test_hotkey_edit_hides_hint_for_supported_chord() -> None:
    edit = HotkeyEdit()
    edit._edit.setKeySequence(_chord(CTRL, Qt.Key.Key_A))
    assert edit._hint.isHidden()
