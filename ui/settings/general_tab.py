"""
The General settings tab: the summon hotkey, starting at sign-in, the daily model-call cap and
which actions run without asking. Owns editing these values in memory — except autostart,
which takes effect the moment it's toggled because it isn't an engine setting.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QCheckBox, QFormLayout, QSpinBox, QVBoxLayout, QWidget

from core.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from core.exceptions import AutostartError
from core.logger import get_logger
from models.api import UsageView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.hotkey_edit import HotkeyEdit
from ui.settings.label_roles import styled_label

logger = get_logger(__name__)

ACTION_LABELS: dict[str, str] = {
    "open_app": "Open apps",
    "open_file": "Open files",
    "reveal_in_explorer": "Show files in File Explorer",
    "open_website": "Open websites",
    "open_windows_setting": "Open Windows settings pages",
    "save_note": "Save notes",
}
MAX_DAILY_CALLS = 10_000
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
        self._autostart_box = QCheckBox("Start Nimbus when I sign in")
        self._autostart_error = styled_label("", "error", wrap=True)
        self._autostart_error.hide()
        self._cap_box = QSpinBox()
        self._cap_box.setRange(0, MAX_DAILY_CALLS)
        self._cap_box.setSpecialValueText(NO_LIMIT_TEXT)
        self._usage_label = styled_label("", "muted")
        self._action_boxes = {tool: QCheckBox(label) for tool, label in ACTION_LABELS.items()}
        self._build_layout()
        self._autostart_box.toggled.connect(self._on_autostart_toggled)

    def _build_layout(self) -> None:
        form = QFormLayout()
        form.addRow("Summon hotkey", self._hotkey_edit)
        form.addRow("Daily model calls", self._cap_box)
        form.addRow("", self._usage_label)
        layout = QVBoxLayout(self)
        layout.addWidget(styled_label("Startup", "section"))
        layout.addWidget(self._autostart_box)
        layout.addWidget(self._autostart_error)
        layout.addSpacing(8)
        layout.addWidget(styled_label("Shortcuts and limits", "section"))
        layout.addLayout(form)
        layout.addSpacing(8)
        layout.addWidget(styled_label("Actions that don't need my approval", "section"))
        for box in self._action_boxes.values():
            layout.addWidget(box)
        layout.addStretch(1)

    def load(self, values: dict[str, Any]) -> None:
        """Fills the tab from saved settings and the real Startup-folder state."""
        self._hotkey_edit.set_hotkey(str(values.get("hotkey", "")))
        self._cap_box.setValue(values.get("daily_llm_call_cap") or 0)
        approved = set(values.get("auto_approved_tools", []))
        for tool, box in self._action_boxes.items():
            box.setChecked(tool in approved)
        self._autostart_box.blockSignals(True)
        self._autostart_box.setChecked(is_autostart_enabled())
        self._autostart_box.blockSignals(False)
        self._autostart_error.hide()
        run_in_background(self._api.usage, self._show_usage)

    def collect(self) -> dict[str, Any]:
        """The edited values; an unusable hotkey is left out so the saved one stays."""
        updates: dict[str, Any] = {
            "daily_llm_call_cap": self._cap_box.value() or None,
            "auto_approved_tools": [tool for tool, box in self._action_boxes.items() if box.isChecked()],
        }
        hotkey = self._hotkey_edit.hotkey()
        if hotkey:
            updates["hotkey"] = hotkey
        return updates

    def _on_autostart_toggled(self, enabled: bool) -> None:
        """Applies the change right away; on failure, puts the box back and says why."""
        try:
            apply_autostart(enabled)
        except AutostartError as e:
            logger.warning("Autostart change failed", extra={"enabled": enabled, "error": str(e)})
            self._autostart_box.blockSignals(True)
            self._autostart_box.setChecked(not enabled)
            self._autostart_box.blockSignals(False)
            self._autostart_error.setText(str(e))
            self._autostart_error.show()
            return
        self._autostart_error.hide()

    def _show_usage(self, usage: UsageView) -> None:
        self._usage_label.setText(describe_usage(usage))
