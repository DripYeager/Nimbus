"""
The list of MCP servers whose tools Nimbus may use: one row per server (name, command, how it's
doing, remove), and a small form to add one from a command line like the ones MCP servers
publish ("npx -y @modelcontextprotocol/server-filesystem C:\\Notes"). Owns editing the list in
memory; saving is the Settings page's job and connecting is the engine's.
"""

from __future__ import annotations

import shlex
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from models.api import McpServerStatus
from ui.settings.label_roles import set_state, styled_label
from ui.settings.section_layout import CARD_ROW_SPACING, GAP, SettingsCard, divider, icon_label
from ui.theme.line_icons import line_icon
from ui.theme.tokens import DANGER, ICON_SIZE, TEXT_MUTED

ICON_BUTTON_SIZE = 30
NAME_BOX_WIDTH = 130
EMPTY_TEXT = "No apps added yet."
NOT_SAVED_TEXT = "Starts when you save"
STATUS_TEXT = {"starting": ("Starting...", "muted"), "failed": ("Couldn't start", "error")}
RETRY_HINT = "Save changes again to retry."


def split_command_line(text: str) -> tuple[str, list[str]]:
    """'npx -y "@scope/server" "C:\\My Notes"' -> ("npx", ["-y", "@scope/server", "C:\\My Notes"]).
    Windows-style: backslashes stay as typed, double quotes group words."""
    parts = [
        part[1:-1] if len(part) > 1 and part[0] == part[-1] == '"' else part for part in shlex.split(text, posix=False)
    ]
    if not parts:
        raise ValueError("Type the command that starts the app's MCP server.")
    return parts[0], parts[1:]


def describe_status(status: McpServerStatus | None) -> tuple[str, str]:
    """The row's status text and its tone."""
    if status is None:
        return NOT_SAVED_TEXT, "muted"
    if status.status == "ready":
        return f"Connected, {status.tool_count} tool{'' if status.tool_count == 1 else 's'}", "success"
    text, tone = STATUS_TEXT.get(status.status, (status.status, "muted"))
    if status.status == "failed":
        reason = f"{text}: {status.error}" if status.error else text
        return f"{reason} {RETRY_HINT}", tone
    return (f"{text}: {status.error}" if status.error else text), tone


class McpServerList(QWidget):
    """load() the saved servers, collect() the edited list, show_status() what the engine says."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._servers: list[dict[str, Any]] = []
        self._statuses: dict[str, McpServerStatus] = {}
        self._card = SettingsCard()
        self._name_box = QLineEdit()
        self._name_box.setPlaceholderText("Name, e.g. github")
        self._name_box.setFixedWidth(NAME_BOX_WIDTH)
        self._command_box = QLineEdit()
        self._command_box.setPlaceholderText("Command, e.g. npx -y @modelcontextprotocol/server-memory")
        self._add_button = QPushButton("Add")
        self._error = styled_label("", "error", wrap=True)
        self._error.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)
        layout.addWidget(self._card)
        layout.addLayout(self._build_form())
        layout.addWidget(self._error)
        self._add_button.clicked.connect(self._add)
        self._command_box.returnPressed.connect(self._add)
        self._render()

    def _build_form(self) -> QHBoxLayout:
        form = QHBoxLayout()
        form.setSpacing(CARD_ROW_SPACING)
        form.addWidget(self._name_box)
        form.addWidget(self._command_box, 1)
        form.addWidget(self._add_button)
        return form

    def load(self, servers: list[dict[str, Any]]) -> None:
        self._servers = [dict(server) for server in servers]
        self._error.hide()
        self._render()

    def collect(self) -> list[dict[str, Any]]:
        """The servers as edited, keeping fields this page doesn't show (such as env)."""
        return [dict(server) for server in self._servers]

    def show_status(self, statuses: list[McpServerStatus]) -> None:
        self._statuses = {status.name: status for status in statuses}
        self._render()

    def _add(self) -> None:
        name = self._name_box.text().strip()
        try:
            command, args = split_command_line(self._command_box.text().strip())
            self._check_name(name)
        except ValueError as e:
            self._show_error(str(e))
            return
        self._servers.append({"name": name, "command": command, "args": args, "env": {}, "enabled": True})
        self._name_box.clear()
        self._command_box.clear()
        self._error.hide()
        self._render()

    def _check_name(self, name: str) -> None:
        if not name:
            raise ValueError("Give the app a short name; its tools are named after it.")
        if any(server["name"].lower() == name.lower() for server in self._servers):
            raise ValueError(f"There's already an app called {name}.")

    def _remove(self, name: str) -> None:
        self._servers = [server for server in self._servers if server["name"] != name]
        self._render()

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _render(self) -> None:
        """Rebuilds the card's rows from the list."""
        while self._card.body.count():
            item = self._card.body.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not self._servers:
            self._card.body.addWidget(styled_label(EMPTY_TEXT, "muted"))
        for index, server in enumerate(self._servers):
            if index:
                self._card.body.addWidget(divider())
            self._card.body.addWidget(self._row(server))

    def _row(self, server: dict[str, Any]) -> QWidget:
        """Icon, name over command and status, and a remove button."""
        command = " ".join([server.get("command", ""), *server.get("args", [])])
        text, tone = describe_status(self._statuses.get(server["name"]))
        status = styled_label(text, None, wrap=True)
        set_state(status, tone)
        title = QLabel(server["name"])
        title.setObjectName("RowTitle")
        column = QVBoxLayout()
        column.setSpacing(2)
        for widget in (title, styled_label(command, "muted", wrap=True), status):
            column.addWidget(widget)
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CARD_ROW_SPACING)
        layout.addWidget(icon_label("plug"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(column, 1)
        layout.addWidget(self._remove_button(server["name"]), 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _remove_button(self, name: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("IconButton")
        button.setIcon(line_icon("trash-2", TEXT_MUTED, ICON_SIZE, hover_color=DANGER))
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        button.setToolTip(f"Remove {name}")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._remove(name))
        return button
