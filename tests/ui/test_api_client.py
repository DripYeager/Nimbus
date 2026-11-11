from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from pytest_mock import MockerFixture

from core.api_auth import auth_headers
from core.exceptions import NimbusError
from models.chat import ProviderConfig
from ui.api_client import DEFAULT_TIMEOUT_SECONDS, PROVIDER_TIMEOUT_SECONDS, UNREACHABLE_MESSAGE, ApiClient

BASE_URL = "http://127.0.0.1:9999"
SETTINGS_BODY = {"values": {"hotkey": "<ctrl>+<space>"}, "has_api_key": {}, "data_dir": "C:/data", "is_cloud": False}


def _response(status_code: int, body: Any = None, text: str | None = None) -> httpx.Response:
    if text is not None:
        return httpx.Response(status_code, text=text)
    return httpx.Response(status_code, json=body)


@pytest.fixture
def request_mock(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.api_client.httpx.request", return_value=_response(200, {}))


@pytest.fixture
def client() -> ApiClient:
    return ApiClient(BASE_URL)


def test_api_client_defaults_to_the_configured_base_url(request_mock: Mock) -> None:
    request_mock.return_value = _response(200, {"calls_today": 0, "daily_cap": None})

    ApiClient().usage()

    assert request_mock.call_args.args[1] == "http://127.0.0.1:8765/usage"


def test_index_status_parses_the_response(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, {"cataloged_files": 7, "is_paused": True})

    status = client.index_status()

    assert (status.cataloged_files, status.is_paused) == (7, True)
    request_mock.assert_called_once_with(
        "GET", f"{BASE_URL}/index/status", json=None, timeout=DEFAULT_TIMEOUT_SECONDS, headers=auth_headers()
    )


def test_source_summaries_parses_each_item(request_mock: Mock, client: ApiClient) -> None:
    item = {"path": "C:/Docs", "include_contents": True, "exists": True, "file_count": 3, "indexed_count": 2}
    request_mock.return_value = _response(200, [item])

    assert [s.path for s in client.source_summaries()] == ["C:/Docs"]


@pytest.mark.parametrize(("paused", "path"), [(True, "/index/pause"), (False, "/index/resume")])
def test_set_paused_posts_to_the_matching_endpoint(
    request_mock: Mock, client: ApiClient, paused: bool, path: str
) -> None:
    client.set_paused(paused)

    assert request_mock.call_args.args == ("POST", f"{BASE_URL}{path}")


def test_rebuild_index_posts_rebuild(request_mock: Mock, client: ApiClient) -> None:
    client.rebuild_index()

    assert request_mock.call_args.args == ("POST", f"{BASE_URL}/index/rebuild")


def test_settings_parses_the_settings_view(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, SETTINGS_BODY)

    assert client.settings().values["hotkey"] == "<ctrl>+<space>"


def test_update_settings_sends_the_updates_as_json(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, SETTINGS_BODY)

    client.update_settings({"hotkey": "<alt>+n"})

    assert request_mock.call_args.args[0] == "PUT"
    assert request_mock.call_args.kwargs["json"] == {"hotkey": "<alt>+n"}


def test_set_api_key_puts_the_key_for_the_provider(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, SETTINGS_BODY)

    client.set_api_key("openai", "sk-test")

    assert request_mock.call_args.args == ("PUT", f"{BASE_URL}/settings/api-keys/openai")
    assert request_mock.call_args.kwargs["json"] == {"api_key": "sk-test"}


def test_test_provider_uses_the_longer_provider_timeout(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, {"ok": True, "message": "Connected", "models": ["m1"]})

    result = client.test_provider(ProviderConfig(name="ollama", model="llama3"))

    assert result.models == ["m1"]
    assert request_mock.call_args.kwargs["timeout"] == PROVIDER_TIMEOUT_SECONDS


def test_usage_parses_the_usage_view(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, {"calls_today": 4, "daily_cap": 50})

    assert client.usage().calls_today == 4


def test_conversations_parses_each_summary(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, [{"id": "c1", "title": "Hi", "updated_at": "2026-11-10T09:30:00"}])

    [summary] = client.conversations()

    assert summary.updated_at == datetime(2026, 11, 10, 9, 30)


def test_conversation_parses_each_message(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, [{"role": "user", "content": "hello"}])

    [message] = client.conversation("c1")

    assert (message.role, message.content) == ("user", "hello")


def test_delete_conversation_sends_delete(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(200, {"deleted": True})

    client.delete_conversation("c1")

    assert request_mock.call_args.args == ("DELETE", f"{BASE_URL}/conversations/c1")


def test_request_raises_friendly_error_when_engine_is_unreachable(request_mock: Mock, client: ApiClient) -> None:
    request_mock.side_effect = httpx.ConnectError("refused")

    with pytest.raises(NimbusError) as error:
        client.index_status()
    assert str(error.value) == UNREACHABLE_MESSAGE


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"error": "Folder not found"}, "Folder not found"),
        ({"detail": "Not Found"}, "Not Found"),
        ({}, "Nimbus returned an error (404)."),
        (["unexpected", "list"], "Nimbus returned an error (404)."),
    ],
)
def test_request_raises_the_api_error_message(request_mock: Mock, client: ApiClient, body: Any, expected: str) -> None:
    request_mock.return_value = _response(404, body)

    with pytest.raises(NimbusError) as error:
        client.index_status()
    assert str(error.value) == expected


def test_request_falls_back_to_status_code_for_non_json_errors(request_mock: Mock, client: ApiClient) -> None:
    request_mock.return_value = _response(502, text="<html>Bad gateway</html>")

    with pytest.raises(NimbusError, match=r"\(502\)"):
        client.index_status()
