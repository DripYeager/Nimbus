"""
HTTP route Settings polls to show how each of the user's MCP servers is doing (starting, ready
with N tools, or failed and why). Routes only delegate; connections live in core/mcp_client.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_services
from core.service_container import AppServices
from models.api import McpServerStatus

router = APIRouter(prefix="/mcp")


@router.get("/servers")
def server_status(services: AppServices = Depends(get_services)) -> list[McpServerStatus]:
    return [
        McpServerStatus(name=state.name, status=state.status, tool_count=len(state.tools), error=state.error)
        for state in services.mcp.states()
    ]
