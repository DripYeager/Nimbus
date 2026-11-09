from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from core.service_container import AppServices
from models.schema import AppEntry

SPOTIFY = AppEntry(name="Spotify", launch_target="C:/Spotify.lnk", source="start_menu")


@pytest.fixture
def launch(mocker: MockerFixture) -> Mock:
    return mocker.patch("api.app_routes.launch_app")


def test_find_apps_returns_the_best_matches(client: TestClient, services: AppServices) -> None:
    services.apps.find.return_value = [(SPOTIFY, 98.0)]

    response = client.get("/apps", params={"q": "spot"})

    assert [a["name"] for a in response.json()] == ["Spotify"]


def test_find_apps_lists_apps_alphabetically_for_a_blank_query(client: TestClient, services: AppServices) -> None:
    services.apps.entries.return_value = [
        AppEntry(name="zoom", launch_target="z", source="registry"),
        AppEntry(name="Excel", launch_target="e", source="start_menu"),
    ]

    response = client.get("/apps", params={"q": "  "})

    assert [a["name"] for a in response.json()] == ["Excel", "zoom"]
    services.apps.find.assert_not_called()


def test_launch_launches_the_top_match(client: TestClient, services: AppServices, launch: Mock) -> None:
    services.apps.find.return_value = [(SPOTIFY, 98.0)]

    response = client.post("/apps/launch", json={"name": "spotify"})

    launch.assert_called_once_with(SPOTIFY)
    assert response.json() == {"launched": True, "app": SPOTIFY.model_dump()}


def test_launch_returns_404_when_no_app_matches(client: TestClient, services: AppServices, launch: Mock) -> None:
    services.apps.find.return_value = []

    response = client.post("/apps/launch", json={"name": "spotify"})

    assert response.status_code == 404
    launch.assert_not_called()
