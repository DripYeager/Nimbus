"""
The UI's typed client for Nimbus's local API (everything except chat streaming, which lives in
chat/chat_stream.py). Plain blocking calls, run slow ones through background_call so the
window never freezes. Owns HTTP plumbing and error translation only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from config.settings import get_settings
from core.api_auth import auth_headers
from core.exceptions import NimbusError
from models.api import (
    DueReminder,
    McpServerStatus,
    ModelRecommendation,
    OllamaStatus,
    ProviderTestResult,
    SettingsView,
    UsageView,
)
from models.chat import ChatMessage, ConversationSummary, ConversationView, ProviderConfig, ProviderName
from models.schema import IndexStatus, SourceSummary

DEFAULT_TIMEOUT_SECONDS = 10.0
# Listing models or reaching a cold provider can legitimately take a while.
PROVIDER_TIMEOUT_SECONDS = 30.0
UNREACHABLE_MESSAGE = "Couldn't reach Nimbus's engine. Try restarting Nimbus from the tray."


class ApiClient:
    """One method per endpoint the UI needs."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().api_base_url

    def index_status(self) -> IndexStatus:
        return IndexStatus(**self._request("GET", "/index/status"))

    def source_summaries(self) -> list[SourceSummary]:
        return [SourceSummary(**item) for item in self._request("GET", "/index/sources")]

    def set_paused(self, paused: bool) -> IndexStatus:
        return IndexStatus(**self._request("POST", "/index/pause" if paused else "/index/resume"))

    def rebuild_index(self) -> IndexStatus:
        return IndexStatus(**self._request("POST", "/index/rebuild"))

    def settings(self) -> SettingsView:
        return SettingsView(**self._request("GET", "/settings"))

    def update_settings(self, updates: dict[str, Any]) -> SettingsView:
        return SettingsView(**self._request("PUT", "/settings", json=updates))

    def set_api_key(self, provider: ProviderName, api_key: str) -> SettingsView:
        return SettingsView(**self._request("PUT", f"/settings/api-keys/{provider}", json={"api_key": api_key}))

    def test_provider(self, config: ProviderConfig) -> ProviderTestResult:
        response = self._request("POST", "/providers/test", json=config.model_dump(), timeout=PROVIDER_TIMEOUT_SECONDS)
        return ProviderTestResult(**response)

    def ollama_status(self, model: str) -> OllamaStatus:
        return OllamaStatus(**self._request("GET", f"/providers/ollama/status?model={quote(model)}"))

    def ollama_recommendation(self) -> ModelRecommendation:
        return ModelRecommendation(**self._request("GET", "/providers/ollama/recommendation"))

    def start_ollama(self) -> OllamaStatus:
        return OllamaStatus(**self._request("POST", "/providers/ollama/start"))

    def pull_ollama_model(self, model: str) -> OllamaStatus:
        return OllamaStatus(**self._request("POST", "/providers/ollama/pull", json={"model": model}))

    def due_reminders(self) -> list[DueReminder]:
        return [DueReminder(**item) for item in self._request("GET", "/reminders/due")]

    def mcp_servers(self) -> list[McpServerStatus]:
        return [McpServerStatus(**item) for item in self._request("GET", "/mcp/servers")]

    def usage(self) -> UsageView:
        return UsageView(**self._request("GET", "/usage"))

    def conversations(self) -> list[ConversationSummary]:
        return [ConversationSummary(**item) for item in self._request("GET", "/conversations")]

    def conversation(self, conversation_id: str) -> list[ChatMessage]:
        return [ChatMessage(**item) for item in self._request("GET", f"/conversations/{conversation_id}")]

    def conversation_view(self, conversation_id: str) -> ConversationView:
        return ConversationView(**self._request("GET", f"/conversations/{conversation_id}/view"))

    def delete_conversation(self, conversation_id: str) -> None:
        self._request("DELETE", f"/conversations/{conversation_id}")

    def _request(self, method: str, path: str, json: Any = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
        """Sends one request; any failure becomes a NimbusError carrying a message fit to show."""
        try:
            response = httpx.request(
                method, f"{self._base_url}{path}", json=json, timeout=timeout, headers=auth_headers()
            )
        except httpx.HTTPError as e:
            raise NimbusError(UNREACHABLE_MESSAGE) from e
        if response.is_error:
            raise NimbusError(_error_message(response))
        return response.json()


def _error_message(response: httpx.Response) -> str:
    """The API's own error text when it sent one, else the status line."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return f"Nimbus returned an error ({response.status_code})."
    return str(body.get("error") or body.get("detail") or f"Nimbus returned an error ({response.status_code}).")
