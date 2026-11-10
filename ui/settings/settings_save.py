"""
Writes edited settings to the engine: the settings themselves and, when one was typed, the
provider's API key. Shared by the Settings page and onboarding; runs on a worker thread and
knows nothing about widgets.
"""

from __future__ import annotations

from typing import Any

from models.chat import ProviderName
from ui.api_client import ApiClient


def save_settings(api: ApiClient, updates: dict[str, Any], provider: ProviderName, api_key: str | None) -> None:
    """Saves updates, then stores api_key for provider; a None key leaves the saved one alone."""
    api.update_settings(updates)
    if api_key:
        api.set_api_key(provider, api_key)
