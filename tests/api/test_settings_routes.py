from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from config.settings import get_settings
from core.exceptions import ProviderError
from core.secret_store import get_api_key, save_api_key
from core.service_container import AppServices
from llm.provider import LLMProvider
from models.chat import ProviderConfig

SECRET_FIELDS = {"openai_api_key", "anthropic_api_key", "compatible_api_key"}


@pytest.fixture
def env_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A developer .env-style key, which must never be echoed back by the API."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret")
    return "sk-env-secret"


@pytest.fixture
def build_provider(mocker: MockerFixture) -> Mock:
    backend = mocker.Mock(spec=LLMProvider)
    backend.list_models.return_value = ["gpt-5-mini", "gpt-5"]
    return mocker.patch("api.settings_routes.build_provider", return_value=backend)


def test_read_settings_omits_key_fields(client: TestClient, env_key: str) -> None:
    response = client.get("/settings")

    assert not SECRET_FIELDS & set(response.json()["values"])
    assert env_key not in response.text


def test_read_settings_reports_which_providers_have_a_key(client: TestClient, env_key: str) -> None:
    has_key = client.get("/settings").json()["has_api_key"]

    assert has_key == {"openai": True, "anthropic": False, "openai_compatible": False}


def test_update_settings_saves_and_applies_the_change(
    client: TestClient, services: AppServices, isolated_home: Path, mocker: MockerFixture
) -> None:
    apply = mocker.patch.object(services, "apply_settings")

    response = client.put("/settings", json={"max_agent_steps": 9})

    assert response.json()["values"]["max_agent_steps"] == 9
    assert get_settings().max_agent_steps == 9
    apply.assert_called_once()


def test_update_settings_never_returns_key_fields(
    client: TestClient, services: AppServices, isolated_home: Path, env_key: str, mocker: MockerFixture
) -> None:
    mocker.patch.object(services, "apply_settings")

    response = client.put("/settings", json={"hotkey": "<ctrl>+<alt>+n"})

    assert not SECRET_FIELDS & set(response.json()["values"])
    assert env_key not in response.text


def test_update_settings_returns_400_for_an_invalid_value(
    client: TestClient, services: AppServices, isolated_home: Path, mocker: MockerFixture
) -> None:
    apply = mocker.patch.object(services, "apply_settings")

    response = client.put("/settings", json={"max_agent_steps": "lots"})

    assert response.status_code == 400
    assert response.json()["type"] == "SettingsError"
    apply.assert_not_called()


def test_update_settings_returns_400_for_an_unknown_key(client: TestClient, isolated_home: Path) -> None:
    assert client.put("/settings", json={"colour": "blue"}).status_code == 400


def test_update_settings_refuses_to_store_a_key_in_settings(client: TestClient, isolated_home: Path) -> None:
    response = client.put("/settings", json={"openai_api_key": "sk-plain-text"})

    assert response.status_code == 400
    assert not (isolated_home / "settings.json").exists()


def test_store_api_key_saves_it_and_reloads_the_provider(client: TestClient, services: AppServices) -> None:
    response = client.put("/settings/api-keys/anthropic", json={"api_key": "sk-ant-new"})

    assert get_api_key("anthropic", get_settings()) == "sk-ant-new"
    assert response.json()["has_api_key"]["anthropic"] is True
    assert "sk-ant-new" not in response.text
    services.provider.reload.assert_called_once()


def test_store_api_key_returns_400_for_a_provider_without_keys(client: TestClient, services: AppServices) -> None:
    response = client.put("/settings/api-keys/ollama", json={"api_key": "x"})

    assert response.status_code == 400
    services.provider.reload.assert_not_called()


def test_store_api_key_returns_400_for_a_blank_key(client: TestClient) -> None:
    assert client.put("/settings/api-keys/openai", json={"api_key": "  "}).status_code == 400


def test_store_api_key_rejects_an_unknown_provider(client: TestClient) -> None:
    assert client.put("/settings/api-keys/skynet", json={"api_key": "x"}).status_code == 422


def test_remove_api_key_deletes_it_and_reloads_the_provider(client: TestClient, services: AppServices) -> None:
    save_api_key("openai", "sk-old")

    response = client.delete("/settings/api-keys/openai")

    assert response.json()["has_api_key"]["openai"] is False
    services.provider.reload.assert_called_once()


def test_test_provider_reports_the_available_models(client: TestClient, build_provider: Mock) -> None:
    response = client.post("/providers/test", json={"name": "openai", "model": "gpt-5", "api_key": "sk-typed"})

    body = response.json()
    assert body["ok"] is True
    assert body["models"] == ["gpt-5-mini", "gpt-5"]


def test_test_provider_falls_back_to_the_stored_key(client: TestClient, build_provider: Mock) -> None:
    save_api_key("openai", "sk-stored")

    client.post("/providers/test", json={"name": "openai", "model": "gpt-5"})

    assert build_provider.call_args.args[0] == ProviderConfig(name="openai", model="gpt-5", api_key="sk-stored")


def test_test_provider_uses_the_typed_ollama_address(client: TestClient, build_provider: Mock) -> None:
    client.post("/providers/test", json={"name": "ollama", "model": "llama3", "base_url": "http://box:11434"})

    assert build_provider.call_args.kwargs["ollama_host"] == "http://box:11434"


def test_test_provider_uses_the_saved_ollama_host_without_a_typed_one(client: TestClient, build_provider: Mock) -> None:
    client.post("/providers/test", json={"name": "ollama", "model": "llama3", "base_url": ""})

    assert build_provider.call_args.kwargs["ollama_host"] is None


def test_test_provider_treats_a_blank_key_as_missing(client: TestClient, build_provider: Mock) -> None:
    save_api_key("openai", "sk-stored")

    client.post("/providers/test", json={"name": "openai", "model": "gpt-5", "api_key": ""})

    assert build_provider.call_args.args[0].api_key == "sk-stored"


def test_test_provider_flags_a_model_the_provider_does_not_offer(client: TestClient, build_provider: Mock) -> None:
    body = client.post("/providers/test", json={"name": "openai", "model": "gpt-9", "api_key": "k"}).json()

    assert body["ok"] is False
    assert "'gpt-9' isn't available" in body["message"]


def test_test_provider_reports_a_connection_failure(client: TestClient, build_provider: Mock) -> None:
    build_provider.return_value.list_models.side_effect = ProviderError("401 Unauthorized")

    body = client.post("/providers/test", json={"name": "openai", "model": "gpt-5", "api_key": "bad"}).json()

    assert body == {"ok": False, "message": "401 Unauthorized", "models": []}


def test_usage_reports_todays_calls_and_the_cap(client: TestClient, services: AppServices) -> None:
    services.usage.calls_today.return_value = 7
    get_settings().daily_llm_call_cap = 50

    assert client.get("/usage").json() == {"calls_today": 7, "daily_cap": 50}
