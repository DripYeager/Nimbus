"""
Request and response bodies used only at the HTTP boundary, settings views, provider tests,
key updates and app launches. Validation only; the engine never imports these.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.schema import AppEntry


class SettingsView(BaseModel):
    """Every non-secret setting, plus which providers already have a key stored."""

    values: dict[str, Any]
    has_api_key: dict[str, bool]
    data_dir: str
    is_cloud: bool


class ApiKeyUpdate(BaseModel):
    api_key: str


class ProviderTestResult(BaseModel):
    ok: bool
    message: str
    models: list[str] = Field(default_factory=list)


class AppLaunchRequest(BaseModel):
    name: str


class AppLaunchResult(BaseModel):
    launched: bool
    app: AppEntry


class UsageView(BaseModel):
    calls_today: int
    daily_cap: int | None


class ModelRecommendation(BaseModel):
    """The local model suggested for this PC, and why."""

    model: str
    size_gb: float
    reason: str
    hardware: str
    installed: bool = False


class OllamaStatus(BaseModel):
    """Everything the Settings page needs to walk someone from "no Ollama" to "ready"."""

    installed: bool
    running: bool
    models: list[str] = Field(default_factory=list)
    has_model: bool = False
    pulling: str | None = None
    pull_percent: float | None = None
    pull_error: str | None = None


class OllamaPullRequest(BaseModel):
    model: str
