"""
Tools from the user's MCP servers, offered to the chat next to Nimbus's own. Each one is named
after its server (github_create_issue), says where it comes from, and asks before every call,
showing the arguments; "Always allow" is still offered, per tool, as the user chose to add that
server. Owns turning a server's tool list into chat tools and keeping the list in step;
connections live in core/mcp_client.py.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from core.logger import get_logger
from core.mcp_client import ExternalTool, McpConnections
from models.chat import ToolResult
from tools.registry import Tool, ToolRegistry, tool_spec

logger = get_logger(__name__)

# Most model APIs cap tool names at 64 characters of letters, digits, _ and -.
MAX_TOOL_NAME = 64
MAX_DESCRIPTION = 600
MAX_SHOWN_ARGUMENTS = 400
_NOT_ALLOWED_IN_NAME = re.compile(r"[^A-Za-z0-9_-]+")


class McpToolbox:
    """Keeps registry's external tools matching what the connected servers offer."""

    def __init__(self, connections: McpConnections, registry: ToolRegistry) -> None:
        self._connections = connections
        self._registry = registry
        self._lock = threading.Lock()
        self._registered: set[str] = set()

    def sync(self) -> None:
        """Drops the tools of servers that went away and adds the ones that came."""
        with self._lock:
            for name in self._registered:
                self._registry.unregister(name)
            self._registered = set()
            for state in self._connections.states():
                for external in state.tools:
                    self._add(external)

    def _add(self, external: ExternalTool) -> None:
        name = chat_tool_name(external.server, external.name)
        if self._registry.get(name) is not None:
            logger.warning("Skipped an MCP tool whose name is taken", extra={"tool": name})
            return
        self._registry.register(
            Tool(
                tool_spec(name, describe_tool(external), parameter_schema(external.input_schema)),
                lambda args, t=external: ToolResult(content=self._connections.call(t.server, t.name, args)),
                lambda args, t=external: describe_call(t, args),
                requires_confirmation=True,
            )
        )
        self._registered.add(name)


def chat_tool_name(server: str, tool: str) -> str:
    """server_tool, with anything a model API wouldn't accept replaced by _."""
    return _NOT_ALLOWED_IN_NAME.sub("_", f"{server}_{tool}").strip("_")[:MAX_TOOL_NAME]


def describe_tool(external: ExternalTool) -> str:
    text = external.description.strip() or external.name
    return f"[From {external.server}] {text}"[:MAX_DESCRIPTION]


def parameter_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The server's argument schema, as an object schema even when it sent something odd."""
    if schema.get("type") != "object":
        return {"type": "object", "properties": {}, "required": []}
    return {**schema, "properties": schema.get("properties") or {}}


def describe_call(external: ExternalTool, arguments: dict[str, Any]) -> str:
    """The approval card: which app, which tool, and exactly what it's sent."""
    shown = json.dumps(arguments, ensure_ascii=False)
    if len(shown) > MAX_SHOWN_ARGUMENTS:
        shown = shown[:MAX_SHOWN_ARGUMENTS] + "..."
    return f"Use {external.name} from {external.server} with {shown}"
