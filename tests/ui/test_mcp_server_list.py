from __future__ import annotations

import pytest

from models.api import McpServerStatus
from ui.settings.mcp_server_list import (
    NOT_SAVED_TEXT,
    RETRY_HINT,
    McpServerList,
    describe_status,
    split_command_line,
)

MEMORY = {"name": "memory", "command": "npx", "args": ["-y", "server-memory"], "env": {"KEY": "v"}, "enabled": True}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("npx -y @modelcontextprotocol/server-memory", ("npx", ["-y", "@modelcontextprotocol/server-memory"])),
        ('uvx server "C:\\My Notes"', ("uvx", ["server", "C:\\My Notes"])),
        ("C:\\Tools\\server.exe --port 3", ("C:\\Tools\\server.exe", ["--port", "3"])),
    ],
)
def test_split_command_line_keeps_windows_paths(text: str, expected: tuple[str, list[str]]) -> None:
    assert split_command_line(text) == expected


def test_split_command_line_empty_is_refused() -> None:
    with pytest.raises(ValueError):
        split_command_line("   ")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, (NOT_SAVED_TEXT, "muted")),
        (McpServerStatus(name="a", status="ready", tool_count=1), ("Connected, 1 tool", "success")),
        (McpServerStatus(name="a", status="ready", tool_count=3), ("Connected, 3 tools", "success")),
        (
            McpServerStatus(name="a", status="failed", error="not found"),
            (f"Couldn't start: not found {RETRY_HINT}", "error"),
        ),
    ],
)
def test_describe_status_wording(status: McpServerStatus | None, expected: tuple[str, str]) -> None:
    assert describe_status(status) == expected


def test_collect_keeps_fields_the_page_does_not_show() -> None:
    servers = McpServerList()
    servers.load([MEMORY])

    assert servers.collect() == [MEMORY]


def test_add_appends_a_server_from_a_command_line() -> None:
    servers = McpServerList()
    servers._name_box.setText("files")
    servers._command_box.setText("npx -y server-filesystem C:\\Notes")

    servers._add()

    assert servers.collect() == [
        {
            "name": "files",
            "command": "npx",
            "args": ["-y", "server-filesystem", "C:\\Notes"],
            "env": {},
            "enabled": True,
        }
    ]
    assert servers._command_box.text() == ""


def test_add_refuses_a_duplicate_name() -> None:
    servers = McpServerList()
    servers.load([MEMORY])
    servers._name_box.setText("Memory")
    servers._command_box.setText("npx other")

    servers._add()

    assert len(servers.collect()) == 1
    assert "already" in servers._error.text()


def test_add_needs_a_name() -> None:
    servers = McpServerList()
    servers._command_box.setText("npx x")

    servers._add()

    assert servers.collect() == [] and "name" in servers._error.text()


def test_remove_drops_the_server() -> None:
    servers = McpServerList()
    servers.load([MEMORY])

    servers._remove("memory")

    assert servers.collect() == []
