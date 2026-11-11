from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.mcp_client import ExternalTool, McpConnections, ServerState
from tools.mcp_tools import (
    MAX_SHOWN_ARGUMENTS,
    MAX_TOOL_NAME,
    McpToolbox,
    chat_tool_name,
    describe_call,
    parameter_schema,
)
from tools.registry import Tool, ToolRegistry, tool_spec

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
ISSUE = ExternalTool("github", "create_issue", "Open an issue", SCHEMA)


@pytest.fixture
def connections() -> Mock:
    fake = Mock(spec=McpConnections)
    fake.states.return_value = [ServerState("github", "ready", [ISSUE])]
    fake.call.return_value = "Issue #12 opened"
    return fake


def _synced(connections: Mock) -> tuple[ToolRegistry, McpToolbox]:
    registry = ToolRegistry()
    toolbox = McpToolbox(connections, registry)
    toolbox.sync()
    return registry, toolbox


def test_sync_registers_tools_that_ask_first(connections: Mock) -> None:
    registry, _ = _synced(connections)
    tool = registry.get("github_create_issue")

    assert tool is not None and tool.needs_confirmation({"title": "x"})
    assert registry.can_always_allow("github_create_issue")
    assert tool.spec.description.startswith("[From github]")


def test_sync_handler_calls_the_server(connections: Mock) -> None:
    registry, _ = _synced(connections)

    result = registry.get("github_create_issue").handler({"title": "Bug"})

    connections.call.assert_called_once_with("github", "create_issue", {"title": "Bug"})
    assert result.content == "Issue #12 opened"


def test_sync_drops_tools_of_servers_that_went_away(connections: Mock) -> None:
    registry, toolbox = _synced(connections)
    connections.states.return_value = []

    toolbox.sync()

    assert registry.get("github_create_issue") is None


def test_sync_never_replaces_a_built_in_tool(connections: Mock) -> None:
    registry = ToolRegistry()
    built_in = Tool(tool_spec("github_create_issue", "mine", {}), Mock(), lambda a: "mine")
    registry.register(built_in)

    McpToolbox(connections, registry).sync()

    assert registry.get("github_create_issue") is built_in


@pytest.mark.parametrize(
    ("server", "tool", "expected"),
    [("github", "create_issue", "github_create_issue"), ("My Notes", "read.file", "My_Notes_read_file")],
)
def test_chat_tool_name_keeps_allowed_characters(server: str, tool: str, expected: str) -> None:
    assert chat_tool_name(server, tool) == expected


def test_chat_tool_name_is_capped() -> None:
    assert len(chat_tool_name("s" * 40, "t" * 40)) == MAX_TOOL_NAME


def test_parameter_schema_repairs_odd_schemas() -> None:
    assert parameter_schema({"type": "string"}) == {"type": "object", "properties": {}, "required": []}
    assert parameter_schema({"type": "object"})["properties"] == {}
    assert parameter_schema(SCHEMA) == SCHEMA


def test_describe_call_shows_server_tool_and_arguments() -> None:
    assert describe_call(ISSUE, {"title": "Bug"}) == 'Use create_issue from github with {"title": "Bug"}'


def test_describe_call_trims_long_arguments() -> None:
    text = describe_call(ISSUE, {"body": "x" * 1000})

    assert text.endswith("...") and len(text) < MAX_SHOWN_ARGUMENTS + 60
