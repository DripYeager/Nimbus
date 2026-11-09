"""
The hotkey picker: records a single key chord and converts it to and from the pynput-style
string Nimbus stores (e.g. "<ctrl>+<space>"). Owns capture and conversion only; registering the
hotkey with the OS is ui/hotkey.py's job.
"""

from __future__ import annotations

import string

from PyQt6.QtCore import QKeyCombination, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QKeySequenceEdit, QVBoxLayout, QWidget

from ui.settings.label_roles import styled_label

# Order matters: it is the order modifiers are written in the stored string.
_MODIFIERS: tuple[tuple[Qt.KeyboardModifier, str], ...] = (
    (Qt.KeyboardModifier.ControlModifier, "<ctrl>"),
    (Qt.KeyboardModifier.AltModifier, "<alt>"),
    (Qt.KeyboardModifier.ShiftModifier, "<shift>"),
    (Qt.KeyboardModifier.MetaModifier, "<win>"),
)
FUNCTION_KEY_COUNT = 12
UNSUPPORTED_HINT = "Use Ctrl, Alt, Shift or Win together with a letter, a digit, Space or F1–F12."


def _build_key_names() -> dict[Qt.Key, str]:
    """Every non-modifier key a hotkey may end with, mapped to its stored name."""
    names = {Qt.Key.Key_Space: "<space>"}
    for offset, letter in enumerate(string.ascii_lowercase):
        names[Qt.Key(Qt.Key.Key_A.value + offset)] = letter
    for offset, digit in enumerate(string.digits):
        names[Qt.Key(Qt.Key.Key_0.value + offset)] = digit
    for number in range(1, FUNCTION_KEY_COUNT + 1):
        names[Qt.Key(Qt.Key.Key_F1.value + number - 1)] = f"<f{number}>"
    return names


_KEY_NAMES = _build_key_names()
_KEYS_BY_NAME = {name: key for key, name in _KEY_NAMES.items()}
_MODIFIERS_BY_NAME = {name: modifier for modifier, name in _MODIFIERS}


def to_hotkey_string(sequence: QKeySequence) -> str:
    """
    Converts a recorded chord to the stored hotkey format.

    Returns "" for anything Nimbus can't register: an empty or multi-chord sequence, a chord
    without a modifier, or a key outside letters, digits, Space and F1–F12.
    """
    if sequence.count() != 1:
        return ""
    combination = sequence[0]
    key_name = _KEY_NAMES.get(combination.key())
    modifiers = combination.keyboardModifiers()
    parts = [name for modifier, name in _MODIFIERS if modifiers & modifier]
    if key_name is None or not parts:
        return ""
    return "+".join([*parts, key_name])


def from_hotkey_string(hotkey: str) -> QKeySequence:
    """Parses a stored hotkey back into a chord; an empty QKeySequence when it isn't valid."""
    *modifier_names, key_name = hotkey.strip().lower().split("+")
    key = _KEYS_BY_NAME.get(key_name)
    if key is None or not modifier_names or any(name not in _MODIFIERS_BY_NAME for name in modifier_names):
        return QKeySequence()
    modifiers = Qt.KeyboardModifier.NoModifier
    for name in modifier_names:
        modifiers |= _MODIFIERS_BY_NAME[name]
    return QKeySequence(QKeyCombination(modifiers, key))


class HotkeyEdit(QWidget):
    """A one-chord key recorder that explains itself when the chord can't be used."""

    hotkey_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._edit = QKeySequenceEdit()
        self._edit.setMaximumSequenceLength(1)
        self._edit.setClearButtonEnabled(True)
        self._hint = styled_label(UNSUPPORTED_HINT, "muted", wrap=True)
        self._hint.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)
        layout.addWidget(self._hint)
        self._edit.keySequenceChanged.connect(self._on_sequence_changed)

    def hotkey(self) -> str:
        """The recorded chord in stored form, or "" when nothing usable is recorded."""
        return to_hotkey_string(self._edit.keySequence())

    def set_hotkey(self, hotkey: str) -> None:
        self._edit.setKeySequence(from_hotkey_string(hotkey))

    def _on_sequence_changed(self, sequence: QKeySequence) -> None:
        """Shows the hint for a recorded-but-unusable chord and announces usable ones."""
        hotkey = to_hotkey_string(sequence)
        self._hint.setVisible(not sequence.isEmpty() and not hotkey)
        self.hotkey_changed.emit(hotkey)
