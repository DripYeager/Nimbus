"""
Loads and validates all application configuration from environment variables and .env.
Does not contain business logic — callers import get_settings() and read typed fields.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WATCHED_DIRS = ["~/Downloads", "~/Desktop", "~/Documents"]


def _expanded(path: str | Path) -> Path:
    """Resolves ~ to the user's home directory."""
    return Path(path).expanduser()


class Settings(BaseSettings):
    """Typed, validated configuration for the whole Nimbus application."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ollama runs fully local, so it's the only provider that never ships file contents off the machine
    llm_provider: Literal["ollama", "deepinfra", "anthropic", "openai"] = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    deepinfra_api_key: str | None = None
    deepinfra_model: str = "deepseek-ai/DeepSeek-V4-Flash-0731"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    embedding_model: str = "all-MiniLM-L6-v2"

    watched_dirs: list[Path] = Field(default_factory=lambda: [_expanded(p) for p in DEFAULT_WATCHED_DIRS])
    max_chunk_size: int = 512
    chunk_overlap: int = 50
    lancedb_path: Path = Path("./data/index")

    hotkey: str = "<ctrl>+<space>"
    # a hard safety backstop, not a typical-response expectation — err generous, since a cloud
    # provider map-reducing over several documents can legitimately take a while to answer
    thinking_timeout_seconds: int = 60

    # host is not configurable on purpose — see api/server.py, it's always 127.0.0.1
    api_port: int = 8765

    @property
    def api_base_url(self) -> str:
        """The loopback-only base URL every API client should call — never a raw host string."""
        return f"http://127.0.0.1:{self.api_port}"

    @field_validator("watched_dirs", mode="before")
    @classmethod
    def _expand_watched_dirs(cls, value: list[str | Path]) -> list[Path]:
        """Lets .env use ~ the same way the defaults do."""
        return [_expanded(p) for p in value]

    @field_validator("lancedb_path", mode="before")
    @classmethod
    def _expand_lancedb_path(cls, value: str | Path) -> Path:
        """Same deal, but for a single path instead of a list."""
        return _expanded(value)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Returns the process-wide Settings singleton, creating it on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
