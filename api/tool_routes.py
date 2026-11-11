"""
HTTP route the MCP bridge calls when another AI app (Claude Desktop, VS Code...) uses one of
Nimbus's shared tools. Only read-only tools are shared, only while the user has "Share with
other AI apps" on, and only with the bridge's own secret (checked in api/server.py). Routes
only delegate; the tools are the same ones the chat uses.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from api.dependencies import get_services
from config.settings import get_settings
from core.exceptions import ToolError
from core.service_container import AppServices
from models.api import SharedToolResult
from models.chat import ToolCall

router = APIRouter(prefix="/tools")

# Look, never touch: nothing here opens, changes or sends anything.
SHARED_TOOLS = frozenset({"search_files", "find_files_by_name", "read_file", "list_recent_files", "get_file_info"})
SHARING_OFF_MESSAGE = "Sharing with other AI apps is turned off in Nimbus's Settings (Connections)."


@router.post("/{name}")
def run_shared_tool(
    name: str, arguments: dict[str, Any] = Body(default_factory=dict), services: AppServices = Depends(get_services)
) -> SharedToolResult:
    if not get_settings().share_with_mcp_apps:
        raise ToolError(SHARING_OFF_MESSAGE)
    if name not in SHARED_TOOLS:
        raise ToolError(f"{name!r} isn't one of the tools Nimbus shares.")
    result = services.tools.execute(ToolCall(id="mcp-bridge", name=name, arguments=arguments))
    return SharedToolResult(content=result.content, is_error=result.is_error)
