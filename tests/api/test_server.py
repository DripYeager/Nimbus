from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from api.server import API_VERSION, app
from core.api_auth import TOKEN_HEADER
from core.exceptions import AppLaunchError, ConversationNotFoundError, ProviderError
from core.service_container import AppServices
from models.schema import AppEntry


def test_health_reports_ok_and_the_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.json() == {"status": "ok", "version": API_VERSION}


def test_error_handler_maps_a_missing_conversation_to_404(client: TestClient, services: AppServices) -> None:
    services.conversations.load.side_effect = ConversationNotFoundError("There's no chat with id x.")

    response = client.get("/conversations/x")

    assert response.status_code == 404
    assert response.json() == {"error": "There's no chat with id x.", "type": "ConversationNotFoundError"}


def test_error_handler_maps_a_client_error_to_400(
    client: TestClient, services: AppServices, mocker: MockerFixture
) -> None:
    services.apps.find.return_value = [(AppEntry(name="Spotify", launch_target="x", source="registry"), 99.0)]
    mocker.patch("api.app_routes.launch_app", side_effect=AppLaunchError("uninstalled"))

    response = client.post("/apps/launch", json={"name": "spotify"})

    assert response.status_code == 400
    assert response.json()["type"] == "AppLaunchError"


def test_error_handler_maps_an_engine_error_to_502(client: TestClient, services: AppServices) -> None:
    services.index.status.side_effect = ProviderError("model offline")

    response = client.get("/index/status")

    assert response.status_code == 502
    assert response.json() == {"error": "model offline", "type": "ProviderError"}


def test_lifespan_uses_already_attached_services(client: TestClient, mocker: MockerFixture) -> None:
    build = mocker.patch("api.server.AppServices.build")

    with client:
        pass

    build.assert_not_called()


def test_lifespan_builds_starts_and_stops_services_when_none_are_attached(mocker: MockerFixture) -> None:
    built = Mock(spec=AppServices)
    mocker.patch("api.server.AppServices.build", return_value=built)

    try:
        with TestClient(app):
            built.start.assert_called_once()
    finally:
        del app.state.services

    built.stop.assert_called_once()


def test_requests_without_the_token_are_refused(client: TestClient) -> None:
    response = client.get("/index/status", headers={TOKEN_HEADER: "guess"})

    assert (response.status_code, response.json()["type"]) == (401, "Unauthorized")


def test_requests_addressed_to_another_host_are_refused(client: TestClient) -> None:
    response = client.get("/index/status", headers={"host": "evil.example:8765"})

    assert response.status_code == 403


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/health", headers={TOKEN_HEADER: ""})

    assert response.status_code == 200
