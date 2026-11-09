from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.legacy_settings import DEEPINFRA_BASE_URL
from config.settings import Settings, get_settings, reload_settings
from models.schema import IndexSource


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A private data folder, so a settings.json written here can't leak into other tests."""
    monkeypatch.setenv("NIMBUS_HOME", str(tmp_path))
    return tmp_path


def _save_json(home: Path, values: dict[str, object]) -> None:
    (home / "settings.json").write_text(json.dumps(values), encoding="utf-8")


def test_settings_defaults_to_the_local_ollama_provider(home: Path) -> None:
    assert Settings().llm_provider == "ollama"


def test_settings_defaults_thinking_timeout_to_two_minutes(home: Path) -> None:
    assert Settings().thinking_timeout_seconds == 120


def test_settings_reads_an_environment_variable(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")

    assert Settings().ollama_model == "qwen3:4b"


def test_settings_json_beats_an_environment_variable(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "from-env")
    _save_json(home, {"ollama_model": "from-ui"})

    assert Settings().ollama_model == "from-ui"


def test_settings_json_beats_a_dotenv_file(home: Path) -> None:
    dotenv = home / ".env"
    dotenv.write_text("OLLAMA_MODEL=from-dotenv\n", encoding="utf-8")
    _save_json(home, {"ollama_model": "from-ui"})

    assert Settings(_env_file=dotenv).ollama_model == "from-ui"


def test_settings_migrates_a_legacy_deepinfra_provider(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepinfra")

    settings = Settings()

    assert settings.llm_provider == "openai_compatible"
    assert settings.compatible_base_url == DEEPINFRA_BASE_URL


def test_settings_migrates_watched_dirs_from_a_legacy_dotenv(home: Path, tmp_path: Path) -> None:
    dotenv = home / ".env"
    work = (tmp_path / "Work").as_posix()
    dotenv.write_text(f'WATCHED_DIRS=["{work}"]\n', encoding="utf-8")

    settings = Settings(_env_file=dotenv)

    assert settings.sources == [IndexSource(path=Path(work))]


def test_settings_expands_a_tilde_in_data_dir(home: Path) -> None:
    assert Settings(data_dir="~/nimbus-data").data_dir == Path.home() / "nimbus-data"


def test_settings_expands_a_tilde_in_a_source_path(home: Path) -> None:
    settings = Settings(sources=[{"path": "~/Projects"}])

    assert settings.sources[0].path == Path.home() / "Projects"


def test_settings_derives_store_paths_from_data_dir(home: Path, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    assert (settings.lancedb_path, settings.catalog_path, settings.conversations_path) == (
        tmp_path / "index",
        tmp_path / "catalog.db",
        tmp_path / "conversations.db",
    )


def test_settings_api_base_url_is_loopback_only(home: Path) -> None:
    assert Settings(api_port=9000).api_base_url == "http://127.0.0.1:9000"


@pytest.mark.parametrize(("provider", "expected"), [("ollama", False), ("openai", True), ("openai_compatible", True)])
def test_settings_is_cloud_provider_flags_off_machine_providers(home: Path, provider: str, expected: bool) -> None:
    assert Settings(llm_provider=provider).is_cloud_provider is expected


def test_settings_rejects_an_unknown_provider(home: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(llm_provider="not-a-provider")


def test_get_settings_returns_the_same_instance_every_call(home: Path) -> None:
    assert get_settings() is get_settings()


def test_reload_settings_picks_up_a_newly_saved_file(home: Path) -> None:
    get_settings()
    _save_json(home, {"ollama_model": "changed"})

    assert reload_settings().ollama_model == "changed"
