"""The Settings window and the editors it's built from."""

from __future__ import annotations

from ui.settings.general_tab import GeneralTab
from ui.settings.hotkey_edit import HotkeyEdit, from_hotkey_string, to_hotkey_string
from ui.settings.model_editor import ModelEditor
from ui.settings.settings_window import SettingsWindow
from ui.settings.sources_editor import SourcesEditor

__all__ = [
    "SettingsWindow",
    "SourcesEditor",
    "ModelEditor",
    "GeneralTab",
    "HotkeyEdit",
    "to_hotkey_string",
    "from_hotkey_string",
]
