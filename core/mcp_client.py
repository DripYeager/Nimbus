"""
Connections to the MCP servers the user added in Settings: each enabled one is started as a
child process (hidden, closed with Nimbus) and kept connected on one background event loop, so
its tools can be listed and called from the chat's worker threads. A server that won't start,
or doesn't answer in time, is marked failed with the reason, without affecting the others.
Owns the processes, sessions and calls; turning tools into chat tools is tools/mcp_tools.py.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp import Client, StdioServerParameters
from mcp_types import CallToolResult, EmbeddedResource, Implementation, TextContent, TextResourceContents

from core.exceptions import ToolError
from core.logger import get_logger
from models.schema import McpServerConfig

logger = get_logger(__name__)

# Generous: the first start of an npx or uvx server downloads it.
CONNECT_TIMEOUT_S = 90.0
CALL_TIMEOUT_S = 120.0
# Extra wait on top of the call's own timeout before the worker thread gives up on the loop.
CALL_GRACE_S = 10.0
# How long a server gets to close by itself before it's cancelled.
CLOSE_TIMEOUT_S = 5.0
MAX_RESULT_CHARS = 12_000
MAX_TOOL_PAGES = 20
CLIENT_INFO = Implementation(name="Nimbus", version="2.1")

STARTING, READY, FAILED = "starting", "ready", "failed"


@dataclass(frozen=True)
class ExternalTool:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ServerState:
    name: str
    status: str = STARTING
    tools: list[ExternalTool] = field(default_factory=list)
    error: str = ""


class McpConnections:
    """Thread-safe. on_change runs (on the background loop) whenever a server's tools appear
    or go away, so the chat's tool list can follow."""

    def __init__(self, on_change: Callable[[], None] = lambda: None) -> None:
        self.on_change = on_change
        self._loop = asyncio.new_event_loop()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._states: dict[str, ServerState] = {}
        self._clients: dict[str, Client] = {}
        self._stops: dict[str, asyncio.Event] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._restart_lock = asyncio.Lock()
        self._configs: list[McpServerConfig] = []

    def start(self, servers: list[McpServerConfig]) -> None:
        """Connects to every enabled server; a changed list replaces the old connections, and
        the same list again retries any server that failed."""
        enabled = [server for server in servers if server.enabled and server.command.strip()]
        if enabled == self._configs and (self._thread is not None or not enabled) and not self._any_failed():
            return
        self._configs = enabled
        self._ensure_loop()
        asyncio.run_coroutine_threadsafe(self._restart(enabled), self._loop)

    def stop(self) -> None:
        """Closes every server (their processes end with them) and the loop."""
        if self._thread is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._restart([]), self._loop)
        try:
            future.result(timeout=CALL_GRACE_S)
        except Exception:
            logger.warning("MCP servers didn't close in time")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=CALL_GRACE_S)
        self._thread = None

    def _any_failed(self) -> bool:
        with self._lock:
            return any(state.status == FAILED for state in self._states.values())

    def states(self) -> list[ServerState]:
        with self._lock:
            return [ServerState(s.name, s.status, list(s.tools), s.error) for s in self._states.values()]

    def call(self, server: str, tool: str, arguments: dict[str, Any]) -> str:
        """Calls tool on server and returns its text; a failure becomes a ToolError."""
        client = self._clients.get(server)
        if client is None:
            raise ToolError(f"{server} isn't connected right now. Check it in Settings, Connections.")
        call = client.call_tool(tool, arguments, read_timeout_seconds=CALL_TIMEOUT_S)
        future = asyncio.run_coroutine_threadsafe(call, self._loop)
        try:
            result = future.result(timeout=CALL_TIMEOUT_S + CALL_GRACE_S)
        except TimeoutError as e:
            future.cancel()
            raise ToolError(f"{server} didn't answer within {CALL_TIMEOUT_S:.0f} seconds.") from e
        except Exception as e:
            raise ToolError(f"{server} couldn't run {tool}: {e}") from e
        return result_text(result)

    def _ensure_loop(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop.run_forever, name="mcp-servers", daemon=True)
            self._thread.start()

    async def _restart(self, servers: list[McpServerConfig]) -> None:
        """Closes every running server (all of them finish first, so none can report into the
        new list), then starts the new list. Restarts take turns: two quick saves must not
        interleave, or the second would lose track of servers the first just started."""
        async with self._restart_lock:
            await self._close_all()
            with self._lock:
                self._states = {server.name: ServerState(server.name) for server in servers}
            self.on_change()
            for server in servers:
                stop = asyncio.Event()
                self._stops[server.name] = stop
                task = asyncio.ensure_future(self._serve(server, stop))
                self._tasks.append(task)
                self._loop.call_later(CONNECT_TIMEOUT_S, self._give_up_if_slow, server.name, task)

    async def _close_all(self) -> None:
        for stop in self._stops.values():
            stop.set()
        if self._tasks:
            _, pending = await asyncio.wait(self._tasks, timeout=CLOSE_TIMEOUT_S)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        self._tasks = []
        self._stops = {}

    async def _serve(self, server: McpServerConfig, stop: asyncio.Event) -> None:
        """Holds one server's connection open until it's asked to stop."""
        try:
            params = StdioServerParameters(command=server.command, args=server.args, env=server.env or None)
            async with Client(params, client_info=CLIENT_INFO, read_timeout_seconds=CALL_TIMEOUT_S) as client:
                tools = await _list_tools(client, server.name)
                self._clients[server.name] = client
                self._set(server.name, READY, tools=tools)
                await stop.wait()
        except asyncio.CancelledError:
            self._set(server.name, FAILED, error=f"It didn't answer within {CONNECT_TIMEOUT_S:.0f} seconds.")
        except Exception as e:
            logger.warning("MCP server failed", extra={"server": server.name, "error": describe_error(e)})
            self._set(server.name, FAILED, error=describe_error(e))
        finally:
            self._clients.pop(server.name, None)

    def _give_up_if_slow(self, name: str, task: asyncio.Future[None]) -> None:
        with self._lock:
            state = self._states.get(name)
        if state is not None and state.status == STARTING:
            task.cancel()

    def _set(self, name: str, status: str, tools: list[ExternalTool] | None = None, error: str = "") -> None:
        with self._lock:
            if name not in self._states:
                return
            self._states[name] = ServerState(name, status, tools or [], error)
        self.on_change()


async def _list_tools(client: Client, server: str) -> list[ExternalTool]:
    """Every tool the server offers, following pages."""
    tools: list[ExternalTool] = []
    cursor: str | None = None
    for _ in range(MAX_TOOL_PAGES):
        page = await client.list_tools(cursor=cursor)
        for tool in page.tools:
            schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
            tools.append(ExternalTool(server, tool.name, tool.description or tool.title or "", schema))
        cursor = page.next_cursor
        if not cursor:
            break
    return tools


def result_text(result: CallToolResult) -> str:
    """The text a tool returned, trimmed; an error result becomes a ToolError."""
    parts = []
    for block in result.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, EmbeddedResource) and isinstance(block.resource, TextResourceContents):
            parts.append(block.resource.text)
        else:
            parts.append(f"[{block.type} content left out]")
    text = "\n".join(parts).strip() or "(The tool returned nothing.)"
    if result.is_error:
        raise ToolError(text[:MAX_RESULT_CHARS])
    return text[:MAX_RESULT_CHARS] + ("\n[Cut short.]" if len(text) > MAX_RESULT_CHARS else "")


def describe_error(error: BaseException) -> str:
    """A one-line reason. anyio groups errors, so the first real one inside is used."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    if isinstance(error, FileNotFoundError):
        return "Its command wasn't found. Check the program is installed and the command is right."
    return str(error) or type(error).__name__
