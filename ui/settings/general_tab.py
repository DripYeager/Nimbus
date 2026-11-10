"""
The General settings section: the summon hotkey, starting at sign-in, the daily model-call cap
and which actions run without asking. Owns editing these values in memory — except autostart,
which takes effect the moment it's toggled because it isn't an engine setting.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QSpinBox, QVBoxLayout, QWidget

from core.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from core.exceptions import AutostartError
from core.logger import get_logger
from models.api import UsageView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.hotkey_edit import HotkeyEdit
from ui.settings.label_roles import styled_label
from ui.settings.section_layout import (
    GAP,
    GROUP_SPACING,
    SettingsCard,
    ToggleRow,
    divider,
    group_header,
    labelled_row,
)

logger = get_logger(__name__)

# (label, icon) per tool that can run without asking.
ACTION_ROWS: dict[str, tuple[str, str]] = {
    "open_app": ("Open apps", "app-window"),
    "open_file": ("Open files", "file"),
    "reveal_in_explorer": ("Show files in File Explorer", "folder-open"),
    "open_website": ("Open websites", "globe"),
    "open_windows_setting": ("Open Windows settings pages", "settings"),
    "save_note": ("Save notes", "notebook-pen"),
}
MAX_DAILY_CALLS = 10_000
CAP_BOX_WIDTH = 110
NO_LIMIT_TEXT = "No limit"


def apply_autostart(enabled: bool) -> None:
    """Adds or removes the sign-in shortcut; raises AutostartError when Windows refuses."""
    if enabled:
        enable_autostart()
    else:
        disable_autostart()


def describe_usage(usage: UsageView) -> str:
    calls = usage.calls_today
    return f"{calls:,} model call{'' if calls == 1 else 's'} today"


class GeneralTab(QWidget):
    """Edits hotkey, daily_llm_call_cap and auto_approved_tools; toggles autostart directly."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._hotkey_edit = HotkeyEdit()
        self._autostart_row = ToggleRow("Start Nimbus when I sign in", icon="monitor", hint="Ready in the tray.")
        self._autostart_switch = self._autostart_row.switch
        self._autostart_error = styled_label("", "error", wrap=True)
        self._autostart_error.hide()
        self._cap_box = QSpinBox()
        self._cap_box.setRange(0, MAX_DAILY_CALLS)
        self._cap_box.setSpecialValueText(NO_LIMIT_TEXT)
        self._cap_box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._cap_box.setFixedWidth(CAP_BOX_WIDTH)
        self._usage_label = styled_label("", "muted")
        self._action_rows = {tool: ToggleRow(label, icon=icon) for tool, (label, icon) in ACTION_ROWS.items()}
        self._build_layout()
        self._autostart_switch.toggled.connect(self._on_autostart_toggled)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)
        layout.addWidget(group_header("Summon and startup"))
        layout.addWidget(self._build_summon_card())
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Limits"))
        limits = SettingsCard()
        limits.body.addLayout(labelled_row("battery-medium", "Daily model calls", self._usage_label, self._cap_box))
        layout.addWidget(limits)
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Actions that don't need my approval", "Nimbus asks before anything else."))
        layout.addWidget(self._build_actions_card())
        layout.addStretch(1)

    def _build_summon_card(self) -> SettingsCard:
        card = SettingsCard()
        hint = styled_label("Click the key, then press a new chord.", "muted")
        card.body.addLayout(labelled_row("keyboard", "Summon hotkey", hint, self._hotkey_edit))
        card.body.addWidget(divider())
        card.body.addWidget(self._autostart_row)
        card.body.addWidget(self._autostart_error)
        return card

    def _build_actions_card(self) -> SettingsCard:
        card = SettingsCard()
        for index, row in enumerate(self._action_rows.values()):
            if index:
                card.body.addWidget(divider())
            card.body.addWidget(row)
        return card

    def load(self, values: dict[str, Any]) -> None:
        """Fills the section from saved settings and the real Startup-folder state."""
        self._hotkey_edit.set_hotkey(str(values.get("hotkey", "")))
        self._cap_box.setValue(values.get("daily_llm_call_cap") or 0)
        approved = set(values.get("auto_approved_tools", []))
        for tool, row in self._action_rows.items():
            row.switch.setChecked(tool in approved)
        self._autostart_switch.blockSignals(True)
        self._autostart_switch.setChecked(is_autostart_enabled())
        self._autostart_switch.blockSignals(False)
        self._autostart_error.hide()
        run_in_background(self._api.usage, self._show_usage)

    def collect(self) -> dict[str, Any]:
        """The edited values; an unusable hotkey is left out so the saved one stays."""
        updates: dict[str, Any] = {
            "daily_llm_call_cap": self._cap_box.value() or None,
            "auto_approved_tools": [tool for tool, row in self._action_rows.items() if row.switch.isChecked()],
        }
        hotkey = self._hotkey_edit.hotkey()
        if hotkey:
            updates["hotkey"] = hotkey
        return updates

    def _on_autostart_toggled(self, enabled: bool) -> None:
        """Applies the change right away; on failure, puts the switch back and says why."""
        try:
            apply_autostart(enabled)
        except AutostartError as e:
            logger.warning("Autostart change failed", extra={"enabled": enabled, "error": str(e)})
            self._autostart_switch.blockSignals(True)
            self._autostart_switch.setChecked(not enabled)
            self._autostart_switch.blockSignals(False)
            self._autostart_error.setText(str(e))
            self._autostart_error.show()
            return
        self._autostart_error.hide()

    def _show_usage(self, usage: UsageView) -> None:
        self._usage_label.setText(describe_usage(usage))
