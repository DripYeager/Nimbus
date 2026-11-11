"""
The Connections settings section (MCP, the standard way AI apps share tools). Two directions:
let other AI apps (Claude Desktop, VS Code...) search and read the user's shared folders through
Nimbus, with the setup text to paste into them; and add other apps' MCP servers, whose tools
Nimbus may then use, asking first. Owns these fields in memory and the status refresh; saving
is the Settings page's job.
"""

from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from core.mcp_server import SERVER_NAME, launch_command
from models.api import McpServerStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.label_roles import styled_label
from ui.settings.mcp_server_list import McpServerList
from ui.settings.section_layout import GAP, GROUP_SPACING, SettingsCard, ToggleRow, divider, group_header

SNIPPET_LINES = 8
COPIED_TEXT = "Copied"
COPY_TEXT = "Copy setup"
COPIED_FLASH_MS = 2000
# Servers take a few seconds to start, so the status is checked again a few times after a save.
STATUS_CHECKS_MS = (1500, 5000, 12000, 30000)
SHARE_HINT = (
    "Claude Desktop, VS Code and other MCP apps can search and read the folders you shared with Nimbus, "
    "while Nimbus is running. They can't open, change or delete anything."
)
SNIPPET_HINT = (
    "Paste this into the other app's MCP settings. In Claude Desktop: Settings, Developer, Edit Config, "
    "then restart it."
)


def setup_snippet() -> str:
    """The JSON other apps use to start Nimbus's bridge."""
    command, args = launch_command()
    return json.dumps({"mcpServers": {SERVER_NAME: {"command": command, "args": args}}}, indent=2)


class ConnectionsTab(QWidget):
    """Edits share_with_mcp_apps and mcp_servers."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._share_row = ToggleRow("Share with other AI apps", icon="search", hint=SHARE_HINT)
        self._snippet = QPlainTextEdit(setup_snippet())
        self._snippet.setReadOnly(True)
        self._snippet.setFixedHeight(self._snippet.fontMetrics().lineSpacing() * SNIPPET_LINES)
        self._copy_button = QPushButton(COPY_TEXT)
        self._servers = McpServerList()
        self._build_layout()
        self._copy_button.clicked.connect(self._copy_snippet)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)
        layout.addWidget(group_header("Use Nimbus from other apps"))
        layout.addWidget(self._build_share_card())
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(
            group_header("Tools from other apps", "Nimbus asks before every use and shows what it will send.")
        )
        layout.addWidget(self._servers)
        layout.addStretch(1)

    def _build_share_card(self) -> SettingsCard:
        card = SettingsCard()
        card.body.addWidget(self._share_row)
        card.body.addWidget(divider())
        card.body.addWidget(styled_label(SNIPPET_HINT, "muted", wrap=True))
        card.body.addWidget(self._snippet)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._copy_button)
        card.body.addLayout(buttons)
        return card

    def load(self, values: dict[str, Any]) -> None:
        self._share_row.switch.setChecked(bool(values.get("share_with_mcp_apps", False)))
        self._servers.load(list(values.get("mcp_servers", [])))
        self.refresh_status()

    def collect(self) -> dict[str, Any]:
        return {"share_with_mcp_apps": self._share_row.switch.isChecked(), "mcp_servers": self._servers.collect()}

    def refresh_status(self) -> None:
        run_in_background(self._api.mcp_servers, self._show_status, lambda _: None)

    def refresh_after_save(self) -> None:
        """Re-checks a few times while newly added servers start up."""
        for delay in STATUS_CHECKS_MS:
            QTimer.singleShot(delay, self.refresh_status)

    def _show_status(self, statuses: list[McpServerStatus]) -> None:
        self._servers.show_status(statuses)

    def _copy_snippet(self) -> None:
        QGuiApplication.clipboard().setText(self._snippet.toPlainText())
        self._copy_button.setText(COPIED_TEXT)
        QTimer.singleShot(COPIED_FLASH_MS, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._copy_button.setText(COPY_TEXT)
