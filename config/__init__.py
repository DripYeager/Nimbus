"""App-wide configuration, loaded once from .env."""

from __future__ import annotations

from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
