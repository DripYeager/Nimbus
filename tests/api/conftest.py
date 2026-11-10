from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from api.dependencies import get_services
from api.server import app
from core.chat_service import ChatService
from core.conversation_store import ConversationStore
from core.index_service import IndexService
from core.ollama_setup import OllamaSetup
from core.service_container import AppServices
from core.usage_meter import UsageMeter
from llm.active_provider import ActiveProvider
from tools.app_catalog import AppCatalog


@pytest.fixture
def services(mocker: MockerFixture) -> AppServices:
    """A real AppServices shell with every engine service swapped for a mock."""
    services = AppServices()
    services.chat = mocker.Mock(spec=ChatService)
    services.conversations = mocker.Mock(spec=ConversationStore)
    services.index = mocker.Mock(spec=IndexService)
    services.apps = mocker.Mock(spec=AppCatalog)
    services.provider = mocker.Mock(spec=ActiveProvider)
    services.usage = mocker.Mock(spec=UsageMeter)
    services.ollama = mocker.Mock(spec=OllamaSetup)
    return services


@pytest.fixture
def client(services: AppServices) -> Iterator[TestClient]:
    """No `with` block, so the lifespan never runs; app.state.services is set anyway in case it does."""
    app.state.services = services
    app.dependency_overrides[get_services] = lambda: services
    yield TestClient(app)
    app.dependency_overrides.clear()
    del app.state.services


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points saved settings at a per-test folder, so a PUT can't leak into other tests."""
    monkeypatch.setenv("NIMBUS_HOME", str(tmp_path))
    return tmp_path
