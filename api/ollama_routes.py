"""
HTTP routes behind the Settings page's Ollama helper: check status, start Ollama, and download
a model. Routes only delegate to core/ollama_setup.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_services
from config.settings import get_settings
from core.hardware import read_hardware
from core.model_advisor import recommend_model
from core.service_container import AppServices
from models.api import ModelRecommendation, OllamaPullRequest, OllamaStatus

router = APIRouter(prefix="/providers/ollama")


@router.get("/status")
def ollama_status(model: str = "", services: AppServices = Depends(get_services)) -> OllamaStatus:
    """Installed? Running? Has `model` (default: the one in Settings) been downloaded?"""
    return services.ollama.status(model or get_settings().ollama_model)


@router.get("/recommendation")
def recommendation(services: AppServices = Depends(get_services)) -> ModelRecommendation:
    """The local model that fits this PC's RAM and graphics card best."""
    return recommend_model(read_hardware(), services.ollama.installed_models())


@router.post("/start")
def start_ollama(services: AppServices = Depends(get_services)) -> OllamaStatus:
    services.ollama.start()
    return services.ollama.status(get_settings().ollama_model)


@router.post("/pull")
def pull_model(body: OllamaPullRequest, services: AppServices = Depends(get_services)) -> OllamaStatus:
    """Starts the download in the background; poll /status for progress."""
    services.ollama.pull(body.model)
    return services.ollama.status(body.model)
