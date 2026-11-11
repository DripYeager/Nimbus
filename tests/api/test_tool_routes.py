from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from api.dependencies import get_services
from api.server import app
from config.settings_store import save_user_settings
from core.api_auth import TOKEN_HEADER, read_bridge_token, write_bridge_token
from core.mcp_client import McpConnections, ServerState
from core.service_container import AppServices
from models.chat import ToolResult
from tools.registry import ToolRegistry


@pytest.fixture
def bridge_client(services: AppServices, mocker: MockerFixture, tmp_path: Path) -> Iterator[TestClient]:
    """A client holding the bridge's secret instead of the app's."""
    services.tools = mocker.Mock(spec=ToolRegistry)
    services.tools.execute.return_value = ToolResult(content="1. budget.txt")
    write_bridge_token(tmp_path / "token")
    token = read_bridge_token(tmp_path / "token")
    app.state.services = services
    app.dependency_overrides[get_services] = lambda: services
    yield TestClient(app, base_url="http://127.0.0.1", headers={TOKEN_HEADER: token})
    app.dependency_overrides.clear()
    del app.state.services


@pytest.fixture
def sharing_on(isolated_home: Path) -> None:
    save_user_settings({"share_with_mcp_apps": True})


def test_run_shared_tool_runs_a_shared_tool(bridge_client: TestClient, services: AppServices, sharing_on: None) -> None:
    response = bridge_client.post("/tools/search_files", json={"query": "budget"})

    assert response.json() == {"content": "1. budget.txt", "is_error": False}
    call = services.tools.execute.call_args.args[0]
    assert (call.name, call.arguments) == ("search_files", {"query": "budget"})


def test_run_shared_tool_refuses_other_tools(
    bridge_client: TestClient, services: AppServices, sharing_on: None
) -> None:
    response = bridge_client.post("/tools/run_command", json={"command": "dir"})

    assert response.status_code == 400
    services.tools.execute.assert_not_called()


def test_run_shared_tool_refuses_while_sharing_is_off(
    bridge_client: TestClient, services: AppServices, isolated_home: Path
) -> None:
    response = bridge_client.post("/tools/search_files", json={"query": "x"})

    assert response.status_code == 400 and "turned off" in response.json()["error"]
    services.tools.execute.assert_not_called()


def test_bridge_secret_opens_nothing_else(bridge_client: TestClient) -> None:
    assert bridge_client.get("/settings").status_code == 401


def test_app_secret_does_not_open_tools(client: TestClient, sharing_on: None) -> None:
    assert client.post("/tools/search_files", json={"query": "x"}).status_code == 401


def test_server_status_lists_each_server(client: TestClient, services: AppServices, mocker: MockerFixture) -> None:
    services.mcp = mocker.Mock(spec=McpConnections)
    services.mcp.states.return_value = [ServerState("github", "failed", [], "not found")]

    assert client.get("/mcp/servers").json() == [
        {"name": "github", "status": "failed", "tool_count": 0, "error": "not found"}
    ]
