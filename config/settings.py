"""
Loads and validates all application configuration. Values come from, in priority order: the
Settings window's saved JSON file, environment variables, then .env, so a choice made in the
UI always wins over a developer's .env. Does not contain business logic or write anything;
saving lives in settings_store.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from config.legacy_settings import migrate_legacy_values
from config.paths import app_data_dir, user_settings_path
from models.chat import ProviderName
from models.schema import FileCategory, IndexSource, McpServerConfig

DEFAULT_SOURCE_DIRS = ["~/Downloads", "~/Desktop", "~/Documents"]
CLOUD_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "openai_compatible"})


def _expanded(path: str | Path) -> Path:
    """Resolves ~ to the user's home directory."""
    return Path(path).expanduser()


def _default_sources() -> list[IndexSource]:
    """Downloads, Desktop and Documents, contents included, what most people mean by 'my files'."""
    return [IndexSource(path=_expanded(p)) for p in DEFAULT_SOURCE_DIRS]


class Settings(BaseSettings):
    """Typed, validated configuration for the whole Nimbus application."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ollama runs fully local, so it's the only provider that never ships file contents off the machine
    llm_provider: ProviderName = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    # Ollama's own default window is only a few thousand tokens: the system prompt, the tool
    # list and one read document overflow it, Ollama silently drops the start, and the model
    # answers with nothing. 16K fits a long document comfortably on an 8B model.
    ollama_context_tokens: int = 16384
    # Lets thinking models reason before answering: sometimes better, much slower on a laptop.
    ollama_thinking: bool = False
    openai_model: str = "gpt-5-mini"
    anthropic_model: str = "claude-haiku-5-5"
    compatible_base_url: str = ""
    compatible_model: str = ""
    # Developer fallback only. Keys entered in the Settings window go to the OS credential
    # store (core/secret_store.py) and are never written to settings.json.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    compatible_api_key: str | None = None

    # gte-base beat bge-small (0.73 to 0.78 top-1 on paraphrased questions over 100 look-alike
    # documents) with no losses elsewhere; changing it rebuilds the index once.
    embedding_model: str = "thenlper/gte-base"
    embedding_threads: int = 2
    # A cross-encoder that re-scores the top search candidates (downloads 150 MB once). Off by
    # default: with query-aware hybrid search it added no accuracy on the benchmark and cost
    # about 250 ms per question (see the README's retrieval notes).
    rerank_enabled: bool = False
    rerank_model: str = "jinaai/jina-reranker-v1-turbo-en"
    # Local speech-to-text for the microphone button; downloads once (about 150 MB).
    whisper_model: str = "base.en"

    sources: list[IndexSource] = Field(default_factory=_default_sources)
    file_categories: list[FileCategory] = Field(default_factory=lambda: list(FileCategory))
    max_file_size_mb: int = 50
    exclude_patterns: list[str] = Field(default_factory=list)
    # the embedding model reads at most 512 tokens, so a chunk has to stay well under that many words
    max_chunk_size: int = 250
    chunk_overlap: int = 40
    # a short pause between files keeps a first-run index from pinning the CPU
    index_throttle_ms: int = 20
    data_dir: Path = Field(default_factory=app_data_dir)

    hotkey: str = "<ctrl>+<space>"
    # how long the chat waits on a silent engine; the engine sends a heartbeat every few seconds
    # while a model thinks, so slow local models never hit this
    thinking_timeout_seconds: int = 120
    api_port: int = 8765

    daily_llm_call_cap: int | None = None
    auto_approved_tools: list[str] = Field(default_factory=list)
    max_agent_steps: int = 6
    # MCP: let other AI apps search through Nimbus, and use tools from other apps' MCP servers.
    share_with_mcp_apps: bool = False
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    onboarding_complete: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Puts the Settings window's JSON file ahead of env vars and .env."""
        json_settings = JsonConfigSettingsSource(settings_cls, json_file=user_settings_path())
        return init_settings, json_settings, env_settings, dotenv_settings

    @property
    def api_base_url(self) -> str:
        """The loopback-only base URL every API client should call, never a raw host string."""
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def search_index_path(self) -> Path:
        return self.data_dir / "search.db"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def conversations_path(self) -> Path:
        return self.data_dir / "conversations.db"

    @property
    def is_cloud_provider(self) -> bool:
        """True when answers are generated off this machine, drives the privacy badge."""
        return self.llm_provider in CLOUD_PROVIDERS

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        """Accepts a Nimbus 1.x .env instead of refusing to start."""
        return migrate_legacy_values(data) if isinstance(data, dict) else data

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: str | Path) -> Path:
        """Lets .env use ~ in the data folder path."""
        return _expanded(value)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Returns the process-wide Settings singleton, creating it on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Drops the cached Settings and re-reads every source, called after the UI saves a change."""
    global _settings
    _settings = None
    return get_settings()
