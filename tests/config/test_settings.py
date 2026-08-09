from __future__ import annotations

from config.settings import Settings


def test_thinking_timeout_seconds_defaults_to_sixty() -> None:
    settings = Settings(_env_file=None)
    assert settings.thinking_timeout_seconds == 60


def test_thinking_timeout_seconds_is_overridable() -> None:
    settings = Settings(_env_file=None, thinking_timeout_seconds=120)
    assert settings.thinking_timeout_seconds == 120
