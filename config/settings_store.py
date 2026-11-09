"""
Persists changes made in the Settings window to the per-user settings JSON file, validating the
merged result before anything is written. Does not store API keys — those go to the OS
credential store via core/secret_store.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config.paths import user_settings_path
from config.settings import Settings, reload_settings
from core.exceptions import SettingsError

# Keys are deliberately not editable through this path, so a bug in the UI can never write a
# secret into a plain-text file.
FORBIDDEN_KEYS = frozenset({"openai_api_key", "anthropic_api_key", "compatible_api_key"})


def load_user_settings() -> dict[str, Any]:
    """Returns whatever the user has saved so far, or an empty dict on a fresh install."""
    path = user_settings_path()
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SettingsError(f"Couldn't read saved settings at {path}: {e}. Fix or delete the file.") from e
    if not isinstance(saved, dict):
        raise SettingsError(f"Saved settings at {path} aren't a JSON object. Fix or delete the file.")
    return saved


def save_user_settings(updates: dict[str, Any]) -> Settings:
    """Merges updates into the saved settings, validates the result, writes it, and returns
    the freshly reloaded Settings.

    Raises:
        SettingsError: if updates contain an unknown or secret key, or fail validation.
    """
    _reject_unknown_keys(updates)
    merged = {**load_user_settings(), **updates}
    try:
        validated = Settings(_env_file=None, **merged)
    except ValidationError as e:
        raise SettingsError(f"Those settings aren't valid: {e}") from e
    serializable = validated.model_dump(mode="json", include=set(merged))
    try:
        _write_atomically(user_settings_path(), json.dumps(serializable, indent=2))
    except OSError as e:
        raise SettingsError(f"Couldn't save settings to {user_settings_path()}: {e}") from e
    return reload_settings()


def _reject_unknown_keys(updates: dict[str, Any]) -> None:
    """Stops typos and secrets from being silently persisted."""
    unknown = set(updates) - set(Settings.model_fields)
    if unknown:
        raise SettingsError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    secrets = set(updates) & FORBIDDEN_KEYS
    if secrets:
        raise SettingsError("API keys are stored in the credential store, not in settings.json.")


def _write_atomically(path: Path, text: str) -> None:
    """Writes via a temp file so a crash mid-write can't leave a half-written settings file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)
