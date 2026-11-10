"""
HTTP routes for the Settings window: read and save settings, store or remove API keys, test a
provider and list its models, and report today's usage. Routes only delegate to the settings
store, the credential store and the provider factory.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_services
from config.settings import get_settings
from config.settings_store import save_user_settings
from core.exceptions import NimbusError
from core.secret_store import KEYED_PROVIDERS, delete_api_key, get_api_key, has_api_key, save_api_key
from core.service_container import AppServices
from llm.provider import build_provider
from models.api import ApiKeyUpdate, ProviderTestResult, SettingsView, UsageView
from models.chat import ProviderConfig, ProviderName

router = APIRouter()

SECRET_FIELDS = frozenset({"openai_api_key", "anthropic_api_key", "compatible_api_key"})


@router.get("/settings")
def read_settings() -> SettingsView:
    return _settings_view()


@router.put("/settings")
def update_settings(updates: dict[str, Any], services: AppServices = Depends(get_services)) -> SettingsView:
    """Saves the changed settings and applies them to the running app straight away."""
    save_user_settings(updates)
    services.apply_settings()
    return _settings_view()


@router.put("/settings/api-keys/{provider}")
def store_api_key(
    provider: ProviderName, body: ApiKeyUpdate, services: AppServices = Depends(get_services)
) -> SettingsView:
    save_api_key(provider, body.api_key)
    services.provider.reload()
    return _settings_view()


@router.delete("/settings/api-keys/{provider}")
def remove_api_key(provider: ProviderName, services: AppServices = Depends(get_services)) -> SettingsView:
    delete_api_key(provider)
    services.provider.reload()
    return _settings_view()


@router.post("/providers/test")
def test_provider(config: ProviderConfig) -> ProviderTestResult:
    """Checks unsaved provider choices: can we reach it, and which models does it offer? A
    blank key falls back to the stored one, so "Test" works without retyping it."""
    if not config.api_key:
        config = config.model_copy(update={"api_key": get_api_key(config.name, get_settings())})
    try:
        # The Settings window sends the typed Ollama address in base_url, so an unsaved host
        # can be tested before it's saved.
        ollama_host = config.base_url if config.name == "ollama" else None
        provider = build_provider(config, ollama_host=ollama_host or None)
        models = provider.list_models()
    except NimbusError as e:
        return ProviderTestResult(ok=False, message=str(e))
    if config.model and models and config.model not in models:
        message = f"Connected, but {config.model!r} isn't available. Pick one of the listed models."
        return ProviderTestResult(ok=False, message=message, models=models)
    return ProviderTestResult(ok=True, message=f"Connected. {len(models)} model(s) available.", models=models)


@router.get("/usage")
def usage(services: AppServices = Depends(get_services)) -> UsageView:
    return UsageView(calls_today=services.usage.calls_today(), daily_cap=get_settings().daily_llm_call_cap)


def _settings_view() -> SettingsView:
    """The current settings with secrets removed, plus key presence per provider."""
    settings = get_settings()
    values = settings.model_dump(mode="json", exclude=set(SECRET_FIELDS))
    return SettingsView(
        values=values,
        has_api_key={name: has_api_key(name, settings) for name in KEYED_PROVIDERS},
        data_dir=str(settings.data_dir),
        is_cloud=settings.is_cloud_provider,
    )
