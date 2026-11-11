"""
Nimbus as an MCP server, for other AI apps (Claude Desktop, VS Code, Cursor...). They start
"Nimbus.exe --mcp", which speaks MCP over stdin/stdout and forwards each call to the running
Nimbus through its local API, so search uses the same index and model already loaded. Only
read-only tools are offered, and only while "Share with other AI apps" is on. Owns the protocol
side and the forwarding; what each tool does is the engine's business.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from core.api_auth import BRIDGE_TOKEN_FILE, TOKEN_HEADER, read_bridge_token

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

MCP_FLAG = "--mcp"
SERVER_NAME = "nimbus"
BRIDGE_LOG_FILE = "nimbus-mcp.log"
# Searching can load the embedding model the first time, so allow it some time.
REQUEST_TIMEOUT_S = 120.0
NOT_AVAILABLE = (
    "Nimbus isn't running, or sharing is off. Open Nimbus and turn on Settings, Connections, "
    '"Share with other AI apps".'
)
FAILED_MESSAGE = "Nimbus couldn't do that."
INSTRUCTIONS = (
    "Nimbus searches and reads the files on this Windows PC that the user shared with it. "
    "Use search_files for topics, find_files_by_name for names, then read_file for the text."
)
MAIN_SCRIPT = Path(__file__).resolve().parent.parent / "main.py"


class BridgeError(Exception):
    """A call the running Nimbus couldn't answer; the text is shown to the other app."""


def launch_command() -> tuple[str, list[str]]:
    """How another app should start the bridge: the packaged exe, or this Python and main.py."""
    if getattr(sys, "frozen", False):
        return sys.executable, [MCP_FLAG]
    return sys.executable, [str(MAIN_SCRIPT), MCP_FLAG]


class EngineBridge:
    """Forwards one tool call to the running Nimbus. Reads the secret on every call, so it keeps
    working across Nimbus restarts."""

    def __init__(self, port: int, token_file: Path, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = f"http://127.0.0.1:{port}/tools"
        self._token_file = token_file
        self._transport = transport

    async def call(self, tool: str, arguments: dict[str, Any]) -> str:
        token = read_bridge_token(self._token_file)
        if token is None:
            raise BridgeError(NOT_AVAILABLE)
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, transport=self._transport) as client:
                response = await client.post(f"{self._url}/{tool}", json=arguments, headers={TOKEN_HEADER: token})
        except httpx.HTTPError as e:
            raise BridgeError(NOT_AVAILABLE) from e
        return _answer(response)


def _answer(response: httpx.Response) -> str:
    """The tool's text, or a BridgeError carrying the engine's reason."""
    if response.status_code == httpx.codes.UNAUTHORIZED:
        raise BridgeError(NOT_AVAILABLE)
    try:
        body = response.json()
    except ValueError as e:
        raise BridgeError(FAILED_MESSAGE) from e
    if response.is_error or body.get("is_error"):
        raise BridgeError(str(body.get("error") or body.get("content") or FAILED_MESSAGE))
    return str(body.get("content", ""))


def build_server(bridge: EngineBridge) -> MCPServer:
    """The MCP server and its tools; each just forwards to the engine. The MCP SDK is imported
    here, so Settings can use launch_command without loading it."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as McpToolError

    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS)

    async def forward(tool: str, arguments: dict[str, Any]) -> str:
        return await _forward(bridge, tool, arguments, McpToolError)

    @server.tool(description="Search the user's shared files by topic or meaning. Returns files with excerpts.")
    async def search_files(query: str, limit: int = 8) -> str:
        return await forward("search_files", {"query": query, "limit": limit})

    @server.tool(description="Find files by (part of) their name, any file type.")
    async def find_files_by_name(name: str, limit: int = 20) -> str:
        return await forward("find_files_by_name", {"name": name, "limit": limit})

    @server.tool(description="Read the text of one file: a full path, or an exact file name.")
    async def read_file(path: str, max_words: int = 1500) -> str:
        return await forward("read_file", {"path": path, "max_words": max_words})

    @server.tool(description="List files changed in the last N days (1 = today), optionally in one folder.")
    async def list_recent_files(days: int = 1, folder: str = "", limit: int = 20) -> str:
        return await forward("list_recent_files", {"days": days, "folder": folder, "limit": limit})

    return server


async def _forward(bridge: EngineBridge, tool: str, arguments: dict[str, Any], tool_error: type[Exception]) -> str:
    """The SDK's own tool error carries the reason to the other app; anything else would be
    hidden behind "Error executing tool"."""
    try:
        return await bridge.call(tool, arguments)
    except BridgeError as e:
        raise tool_error(str(e)) from e


def run_bridge() -> None:
    """Entry point for Nimbus.exe --mcp: stdout carries the protocol, so logs go elsewhere."""
    from core.logger import log_beside_stdout

    log_beside_stdout(BRIDGE_LOG_FILE)
    attach_stdio()
    from config.settings import get_settings

    settings = get_settings()
    build_server(EngineBridge(settings.api_port, settings.data_dir / BRIDGE_TOKEN_FILE)).run("stdio")


def attach_stdio() -> None:
    """The packaged app is a windowed program, started with no Python-level stdin, stdout or
    stderr; this reconnects them to the pipes the other app passed in. (core/code_sandbox.py
    has its own copy, as it must run without importing anything from Nimbus.)"""
    if sys.stdin is not None and sys.stdout is not None and sys.stderr is not None:
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    for handle_id, name, flags, mode in (
        (-10, "stdin", os.O_RDONLY, "r"),
        (-11, "stdout", os.O_WRONLY, "w"),
        (-12, "stderr", os.O_WRONLY, "w"),
    ):
        handle = kernel32.GetStdHandle(handle_id)
        if getattr(sys, name) is None and handle and handle != -1:
            descriptor = msvcrt.open_osfhandle(handle, flags)
            setattr(sys, name, open(descriptor, mode, encoding="utf-8", closefd=False))  # noqa: SIM115
