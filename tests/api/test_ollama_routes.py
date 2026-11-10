from __future__ import annotations

from fastapi.testclient import TestClient

from core.exceptions import ProviderError
from core.service_container import AppServices
from models.api import OllamaStatus


def test_status_defaults_to_the_model_in_settings(client: TestClient, services: AppServices) -> None:
    services.ollama.status.return_value = OllamaStatus(installed=True, running=True)

    response = client.get("/providers/ollama/status")

    assert response.status_code == 200
    services.ollama.status.assert_called_once_with("llama3.1:8b")


def test_start_reports_a_missing_install_as_an_error(client: TestClient, services: AppServices) -> None:
    services.ollama.start.side_effect = ProviderError("Ollama isn't installed yet.")

    response = client.post("/providers/ollama/start")

    assert response.status_code == 502
    assert response.json()["error"] == "Ollama isn't installed yet."


def test_pull_starts_a_download_of_the_requested_model(client: TestClient, services: AppServices) -> None:
    services.ollama.status.return_value = OllamaStatus(installed=True, running=True, pulling="qwen2.5:7b")

    response = client.post("/providers/ollama/pull", json={"model": "qwen2.5:7b"})

    services.ollama.pull.assert_called_once_with("qwen2.5:7b")
    assert response.json()["pulling"] == "qwen2.5:7b"
