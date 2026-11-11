from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

from core.api_auth import TOKEN_HEADER
from core.mcp_server import MCP_FLAG, NOT_AVAILABLE, BridgeError, EngineBridge, build_server, launch_command

PORT = 8765
# The sync tests below are fine under this mark too; anyio only wraps coroutines.
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _bridge(tmp_path: Path, handler: Any = None, token: str | None = "bridge-secret") -> EngineBridge:
    token_file = tmp_path / "token"
    if token is not None:
        token_file.write_text(token, encoding="utf-8")
    transport = httpx.MockTransport(handler) if handler else None
    return EngineBridge(PORT, token_file, transport)


async def test_call_forwards_tool_and_secret(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": "1. budget.txt", "is_error": False})

    text = await _bridge(tmp_path, handler).call("search_files", {"query": "budget"})

    assert text == "1. budget.txt"
    assert seen[0].url.path == "/tools/search_files"
    assert seen[0].headers[TOKEN_HEADER] == "bridge-secret"
    assert json.loads(seen[0].content) == {"query": "budget"}


async def test_call_without_token_file_says_not_available(tmp_path: Path) -> None:
    with pytest.raises(BridgeError, match="isn't running"):
        await _bridge(tmp_path, token=None).call("search_files", {"query": "x"})


async def test_call_with_stale_token_says_not_available(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, lambda request: httpx.Response(401, json={"error": "wrong token"}))

    with pytest.raises(BridgeError) as error:
        await bridge.call("read_file", {"path": "a"})

    assert str(error.value) == NOT_AVAILABLE


async def test_call_when_engine_is_down_says_not_available(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(BridgeError, match="isn't running"):
        await _bridge(tmp_path, handler).call("read_file", {"path": "a"})


async def test_call_passes_on_the_engines_reason(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, lambda request: httpx.Response(400, json={"error": "outside the shared folders"}))

    with pytest.raises(BridgeError, match="outside the shared folders"):
        await bridge.call("read_file", {"path": "C:/secret.txt"})


async def test_call_with_tool_error_result_raises(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, lambda request: httpx.Response(200, json={"content": "no such file", "is_error": True}))

    with pytest.raises(BridgeError, match="no such file"):
        await bridge.call("read_file", {"path": "a"})


async def test_call_with_non_json_answer_raises(tmp_path: Path) -> None:
    with pytest.raises(BridgeError, match="couldn't do that"):
        await _bridge(tmp_path, lambda request: httpx.Response(500, text="boom")).call("read_file", {"path": "a"})


async def test_build_server_offers_only_read_only_tools(tmp_path: Path) -> None:
    async with Client(build_server(_bridge(tmp_path))) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}

    assert names == {"search_files", "find_files_by_name", "read_file", "list_recent_files"}


async def test_build_server_shows_bridge_errors_to_the_other_app(tmp_path: Path) -> None:
    async with Client(build_server(_bridge(tmp_path, token=None))) as client:
        result = await client.call_tool("search_files", {"query": "x"})

    assert result.is_error
    assert "isn't running" in result.content[0].text


async def test_build_server_returns_tool_text(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, lambda request: httpx.Response(200, json={"content": "hello", "is_error": False}))

    async with Client(build_server(bridge)) as client:
        result = await client.call_tool("read_file", {"path": "a.txt"})

    assert not result.is_error
    assert result.content[0].text == "hello"


def test_launch_command_from_source_runs_main_py() -> None:
    command, args = launch_command()

    assert command == sys.executable
    assert args[-1] == MCP_FLAG and args[0].endswith("main.py")


def test_launch_command_when_packaged_is_the_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert launch_command() == (sys.executable, [MCP_FLAG])
