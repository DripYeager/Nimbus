from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import get_settings
from config.settings_store import load_user_settings, save_user_settings
from core.exceptions import SettingsError


@pytest.fixture
def settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("NIMBUS_HOME", str(tmp_path))
    return tmp_path / "settings.json"


def test_load_user_settings_returns_empty_on_a_fresh_install(settings_file: Path) -> None:
    assert load_user_settings() == {}


def test_load_user_settings_returns_what_was_saved(settings_file: Path) -> None:
    settings_file.write_text('{"hotkey": "<alt>+n"}', encoding="utf-8")

    assert load_user_settings() == {"hotkey": "<alt>+n"}


def test_load_user_settings_raises_settings_error_for_a_corrupt_file(settings_file: Path) -> None:
    settings_file.write_text("{not json", encoding="utf-8")

    with pytest.raises(SettingsError):
        load_user_settings()


def test_save_user_settings_returns_the_reloaded_settings(settings_file: Path) -> None:
    saved = save_user_settings({"hotkey": "<alt>+n"})

    assert saved.hotkey == "<alt>+n"
    assert get_settings() is saved


def test_save_user_settings_writes_only_the_keys_the_user_changed(settings_file: Path) -> None:
    save_user_settings({"hotkey": "<alt>+n"})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"hotkey": "<alt>+n"}


def test_save_user_settings_merges_with_earlier_saves(settings_file: Path) -> None:
    save_user_settings({"hotkey": "<alt>+n"})
    save_user_settings({"max_agent_steps": 3})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"hotkey": "<alt>+n", "max_agent_steps": 3}


def test_save_user_settings_rejects_an_unknown_key(settings_file: Path) -> None:
    with pytest.raises(SettingsError, match="hot_key"):
        save_user_settings({"hot_key": "<alt>+n"})


@pytest.mark.parametrize("key", ["openai_api_key", "anthropic_api_key", "compatible_api_key"])
def test_save_user_settings_refuses_to_write_an_api_key(settings_file: Path, key: str) -> None:
    with pytest.raises(SettingsError):
        save_user_settings({key: "sk-secret"})

    assert not settings_file.exists()


def test_save_user_settings_rejects_an_invalid_value_without_writing(settings_file: Path) -> None:
    settings_file.write_text('{"hotkey": "<alt>+n"}', encoding="utf-8")

    with pytest.raises(SettingsError):
        save_user_settings({"llm_provider": "not-a-provider"})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"hotkey": "<alt>+n"}


def test_save_user_settings_leaves_no_temp_file_behind(settings_file: Path) -> None:
    save_user_settings({"hotkey": "<alt>+n"})

    assert [p.name for p in settings_file.parent.iterdir()] == ["settings.json"]


def test_save_user_settings_keeps_the_old_file_if_the_final_rename_fails(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file.write_text('{"hotkey": "<alt>+n"}', encoding="utf-8")

    def refuse(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(SettingsError, match="disk full"):
        save_user_settings({"hotkey": "<ctrl>+k"})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"hotkey": "<alt>+n"}
