"""
The General settings section: the summon hotkey, starting at sign-in, the File Explorer menu
entry, the daily model-call cap, the memory a Python run may use, and which actions, code and
commands run without asking. Owns editing these values in memory, except autostart and the
Explorer entry, which take effect the moment they're toggled because they're Windows settings,
not engine ones.
"""

from __future__ import annotations

from typing import Any

import psutil
from PyQt6.QtWidgets import QAbstractButton, QDoubleSpinBox, QSpinBox, QVBoxLayout, QWidget

from config.settings import MIN_CODE_MEMORY_MB
from core.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from core.exceptions import AutostartError, ExplorerMenuError
from core.explorer_menu import disable_explorer_menu, enable_explorer_menu, is_explorer_menu_enabled
from core.logger import get_logger
from models.api import UsageView
from tools.registry import approval_group
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
    # One switch for both file-creation tools (see tools.registry.APPROVAL_GROUPS).
    "create_document": ("Create files (Word, Excel, CSV, text)", "file-text"),
}
# (label, icon, hint) for code and commands: off unless the user deliberately turns them on.
# Even on, Python stays in its sandbox and commands never get administrator rights.
CODE_ROWS: dict[str, tuple[str, str, str]] = {
    "run_python": (
        "Run Python code without asking",
        "code",
        "Code still runs in the sandbox: it reads only your shared folders and can't use the network.",
    ),
    "run_command": (
        "Run any PowerShell command without asking",
        "terminal",
        "Commands that change things run straight away too. Only turn this on if you trust your model.",
    ),
}
CODE_GROUP_HINT = "You still see every command and program in the chat."
MAX_DAILY_CALLS = 10_000
CAP_BOX_WIDTH = 110
MB_PER_GB = 1024
MEMORY_STEP_GB = 0.25
DEFAULT_CODE_MEMORY_MB = 2048
NO_LIMIT_TEXT = "No limit"


def apply_autostart(enabled: bool) -> None:
    """Adds or removes the sign-in shortcut; raises AutostartError when Windows refuses."""
    if enabled:
        enable_autostart()
    else:
        disable_autostart()


def apply_explorer_menu(enabled: bool) -> None:
    """Adds or removes the right-click entry; raises ExplorerMenuError when Windows refuses."""
    if enabled:
        enable_explorer_menu()
    else:
        disable_explorer_menu()


def describe_usage(usage: UsageView) -> str:
    calls = usage.calls_today
    return f"{calls:,} model call{'' if calls == 1 else 's'} today"


def cap_box() -> QSpinBox:
    """Model calls per day; 0 shows as "No limit"."""
    box = QSpinBox()
    box.setRange(0, MAX_DAILY_CALLS)
    box.setSpecialValueText(NO_LIMIT_TEXT)
    box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    box.setFixedWidth(CAP_BOX_WIDTH)
    return box


def memory_box() -> QDoubleSpinBox:
    """Gigabytes, in quarter steps, from the smallest workable limit up to this PC's RAM."""
    box = QDoubleSpinBox()
    box.setDecimals(2)
    box.setSingleStep(MEMORY_STEP_GB)
    box.setRange(MIN_CODE_MEMORY_MB / MB_PER_GB, total_memory_gb())
    box.setSuffix(" GB")
    box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    box.setFixedWidth(CAP_BOX_WIDTH)
    return box


def total_memory_gb() -> float:
    return psutil.virtual_memory().total / MB_PER_GB**3


def describe_memory() -> str:
    return f"A Python run stops if it needs more. This PC has {total_memory_gb():.0f} GB."


class GeneralTab(QWidget):
    """Edits hotkey, daily_llm_call_cap, code_memory_limit_mb and auto_approved_tools (keeping
    tools allowed from a card that have no switch here); toggles autostart directly."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._hotkey_edit = HotkeyEdit()
        self._autostart_row = ToggleRow("Start Nimbus when I sign in", icon="monitor", hint="Ready in the tray.")
        self._autostart_switch = self._autostart_row.switch
        self._autostart_error = styled_label("", "error", wrap=True)
        self._autostart_error.hide()
        self._explorer_row = ToggleRow(
            "Ask Nimbus from File Explorer",
            icon="folder-open",
            hint="Right-click any file. On Windows 11: Show more options.",
        )
        self._explorer_error = styled_label("", "error", wrap=True)
        self._explorer_error.hide()
        self._cap_box = cap_box()
        self._usage_label = styled_label("", "muted")
        self._memory_box = memory_box()
        self._action_rows = {tool: ToggleRow(label, icon=icon) for tool, (label, icon) in ACTION_ROWS.items()}
        self._code_rows = {
            tool: ToggleRow(label, icon=icon, hint=hint) for tool, (label, icon, hint) in CODE_ROWS.items()
        }
        # Tools allowed from an approval card that have no switch here (an MCP tool, say).
        self._other_approved: list[str] = []
        self._build_layout()
        self._autostart_switch.toggled.connect(self._on_autostart_toggled)
        self._explorer_row.switch.toggled.connect(self._on_explorer_toggled)

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
        limits.body.addWidget(divider())
        memory_hint = styled_label(describe_memory(), "muted", wrap=True)
        limits.body.addLayout(labelled_row("cpu", "Memory for Python runs", memory_hint, self._memory_box))
        layout.addWidget(limits)
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Actions that don't need my approval", "Nimbus asks before anything else."))
        layout.addWidget(_rows_card(self._action_rows))
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Code and commands that don't need my approval", CODE_GROUP_HINT))
        layout.addWidget(_rows_card(self._code_rows))
        layout.addStretch(1)

    def _build_summon_card(self) -> SettingsCard:
        card = SettingsCard()
        hint = styled_label("Click the key, then press a new chord.", "muted")
        card.body.addLayout(labelled_row("keyboard", "Summon hotkey", hint, self._hotkey_edit))
        card.body.addWidget(divider())
        card.body.addWidget(self._autostart_row)
        card.body.addWidget(self._autostart_error)
        card.body.addWidget(divider())
        card.body.addWidget(self._explorer_row)
        card.body.addWidget(self._explorer_error)
        return card

    def load(self, values: dict[str, Any]) -> None:
        """Fills the section from saved settings and the real Startup-folder state."""
        self._hotkey_edit.set_hotkey(str(values.get("hotkey", "")))
        self._cap_box.setValue(values.get("daily_llm_call_cap") or 0)
        self._memory_box.setValue(int(values.get("code_memory_limit_mb") or DEFAULT_CODE_MEMORY_MB) / MB_PER_GB)
        approved = list(values.get("auto_approved_tools", []))
        rows = self._switch_rows()
        for tool, row in rows.items():
            row.switch.setChecked(any(name in approved for name in approval_group(tool)))
        shown = {name for tool in rows for name in approval_group(tool)}
        self._other_approved = [name for name in approved if name not in shown]
        _set_quietly(self._autostart_switch, is_autostart_enabled())
        _set_quietly(self._explorer_row.switch, is_explorer_menu_enabled())
        self._autostart_error.hide()
        self._explorer_error.hide()
        run_in_background(self._api.usage, self._show_usage)

    def collect(self) -> dict[str, Any]:
        """The edited values; an unusable hotkey is left out so the saved one stays."""
        updates: dict[str, Any] = {
            "daily_llm_call_cap": self._cap_box.value() or None,
            "code_memory_limit_mb": round(self._memory_box.value() * MB_PER_GB),
            "auto_approved_tools": [
                *self._other_approved,
                *(
                    name
                    for tool, row in self._switch_rows().items()
                    if row.switch.isChecked()
                    for name in approval_group(tool)
                ),
            ],
        }
        hotkey = self._hotkey_edit.hotkey()
        if hotkey:
            updates["hotkey"] = hotkey
        return updates

    def _switch_rows(self) -> dict[str, ToggleRow]:
        return {**self._action_rows, **self._code_rows}

    def _on_autostart_toggled(self, enabled: bool) -> None:
        """Applies the change right away; on failure, puts the switch back and says why."""
        try:
            apply_autostart(enabled)
        except AutostartError as e:
            logger.warning("Autostart change failed", extra={"enabled": enabled, "error": str(e)})
            _set_quietly(self._autostart_switch, not enabled)
            self._autostart_error.setText(str(e))
            self._autostart_error.show()
            return
        self._autostart_error.hide()

    def _on_explorer_toggled(self, enabled: bool) -> None:
        """Same as autostart: immediate, and undone on screen if Windows refuses."""
        try:
            apply_explorer_menu(enabled)
        except ExplorerMenuError as e:
            logger.warning("Explorer menu change failed", extra={"enabled": enabled, "error": str(e)})
            _set_quietly(self._explorer_row.switch, not enabled)
            self._explorer_error.setText(str(e))
            self._explorer_error.show()
            return
        self._explorer_error.hide()

    def _show_usage(self, usage: UsageView) -> None:
        self._usage_label.setText(describe_usage(usage))


def _rows_card(rows: dict[str, ToggleRow]) -> SettingsCard:
    card = SettingsCard()
    for index, row in enumerate(rows.values()):
        if index:
            card.body.addWidget(divider())
        card.body.addWidget(row)
    return card


def _set_quietly(switch: QAbstractButton, checked: bool) -> None:
    """Moves a switch without firing its toggled handler."""
    switch.blockSignals(True)
    switch.setChecked(checked)
    switch.blockSignals(False)
