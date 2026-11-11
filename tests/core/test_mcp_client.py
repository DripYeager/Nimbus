from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp_types import CallToolResult, EmbeddedResource, ImageContent, TextContent, TextResourceContents

from core.exceptions import ToolError
from core.mcp_client import FAILED, MAX_RESULT_CHARS, READY, McpConnections, describe_error, result_text
from core.mcp_server import launch_command
from models.schema import McpServerConfig

WAIT_S = 60.0


@pytest.fixture
def connections() -> Iterator[McpConnections]:
    made = McpConnections()
    yield made
    made.stop()


def _bridge_config(home: Path, name: str = "nimbus") -> McpServerConfig:
    """Nimbus's own MCP bridge as a real stdio server, pointed at a throwaway home."""
    command, args = launch_command()
    return McpServerConfig(name=name, command=command, args=args, env={"NIMBUS_HOME": str(home)})


def _wait_until_settled(connections: McpConnections) -> None:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        states = connections.states()
        if states and all(state.status != "starting" for state in states):
            return
        time.sleep(0.1)
    raise AssertionError(f"Servers never settled: {connections.states()}")


def test_start_connects_and_lists_tools(connections: McpConnections, tmp_path: Path) -> None:
    connections.start([_bridge_config(tmp_path)])
    _wait_until_settled(connections)

    state = connections.states()[0]
    assert state.status == READY
    assert {tool.name for tool in state.tools} >= {"search_files", "read_file"}
    assert state.tools[0].input_schema["type"] == "object"


def test_call_returns_the_servers_error_as_tool_error(connections: McpConnections, tmp_path: Path) -> None:
    connections.start([_bridge_config(tmp_path)])
    _wait_until_settled(connections)

    with pytest.raises(ToolError, match="isn't running"):
        connections.call("nimbus", "search_files", {"query": "budget"})


def test_start_marks_a_missing_program_failed(connections: McpConnections) -> None:
    connections.start([McpServerConfig(name="broken", command="no-such-program-nimbus-test")])
    _wait_until_settled(connections)

    state = connections.states()[0]
    assert state.status == FAILED
    assert "wasn't found" in state.error


def test_start_skips_disabled_and_blank_servers(connections: McpConnections) -> None:
    connections.start(
        [McpServerConfig(name="off", command="x", enabled=False), McpServerConfig(name="blank", command=" ")]
    )

    assert connections.states() == []


def test_start_with_a_new_list_replaces_the_old(connections: McpConnections, tmp_path: Path) -> None:
    changes: list[int] = []
    connections.on_change = lambda: changes.append(1)
    connections.start([_bridge_config(tmp_path, "first")])
    _wait_until_settled(connections)

    connections.start([_bridge_config(tmp_path, "second")])
    time.sleep(0.5)
    _wait_until_settled(connections)

    assert [state.name for state in connections.states()] == ["second"]
    assert changes


def test_call_to_unknown_server_is_explained(connections: McpConnections) -> None:
    with pytest.raises(ToolError, match="isn't connected"):
        connections.call("ghost", "anything", {})


def test_stop_without_start_does_nothing() -> None:
    McpConnections().stop()


def test_result_text_joins_text_and_resources() -> None:
    resource = EmbeddedResource(type="resource", resource=TextResourceContents(uri="file:///a.txt", text="from a file"))
    image = ImageContent(type="image", data="AAAA", mime_type="image/png")
    result = CallToolResult(content=[TextContent(type="text", text="hello"), resource, image])

    assert result_text(result) == "hello\nfrom a file\n[image content left out]"


def test_result_text_error_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="bad input"):
        result_text(CallToolResult(content=[TextContent(type="text", text="bad input")], is_error=True))


def test_result_text_trims_long_output() -> None:
    long = CallToolResult(content=[TextContent(type="text", text="x" * (MAX_RESULT_CHARS + 50))])

    assert result_text(long).endswith("[Cut short.]")


def test_result_text_empty_says_so() -> None:
    assert "nothing" in result_text(CallToolResult(content=[]))


def test_describe_error_unwraps_groups() -> None:
    assert describe_error(ExceptionGroup("tasks", [ValueError("real reason")])) == "real reason"


def test_quick_restarts_keep_track_of_every_server(connections: McpConnections, tmp_path: Path) -> None:
    for name in ("one", "two", "three"):
        connections.start([_bridge_config(tmp_path, name)])
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline and [(s.name, s.status) for s in connections.states()] != [("three", READY)]:
        time.sleep(0.1)

    assert [state.name for state in connections.states()] == ["three"]
    assert len(connections._tasks) == 1
    assert [task for task in connections._tasks if not task.done()]
