from __future__ import annotations

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from core.hardware import HardwareProfile
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


def test_recommendation_uses_this_pcs_hardware_and_downloaded_models(
    client: TestClient, services: AppServices, mocker: MockerFixture
) -> None:
    mocker.patch(
        "api.ollama_routes.read_hardware",
        return_value=HardwareProfile(ram_gb=32, gpu_name="NVIDIA RTX 2000 Ada", vram_gb=8.0),
    )
    services.ollama.installed_models.return_value = ["qwen3:8b"]

    body = client.get("/providers/ollama/recommendation").json()

    assert (body["model"], body["installed"]) == ("qwen3:8b", True)
