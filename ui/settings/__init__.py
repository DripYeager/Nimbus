"""The Settings page and the section editors it's built from (also reused by onboarding)."""

from __future__ import annotations

from ui.settings.general_tab import GeneralTab
from ui.settings.hotkey_edit import HotkeyEdit, from_hotkey_string, to_hotkey_string
from ui.settings.model_editor import ModelEditor
from ui.settings.settings_panel import SettingsPanel
from ui.settings.sources_editor import SourcesEditor

__all__ = [
    "SettingsPanel",
    "SourcesEditor",
    "ModelEditor",
    "GeneralTab",
    "HotkeyEdit",
    "to_hotkey_string",
    "from_hotkey_string",
]
