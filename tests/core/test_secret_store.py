from __future__ import annotations

import logging
from pathlib import Path

import pytest
from keyring.errors import KeyringError, PasswordDeleteError

from config.settings import Settings
from core.exceptions import SecretStoreError
from core.secret_store import delete_api_key, get_api_key, has_api_key, save_api_key


@pytest.fixture(autouse=True)
def _private_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keeps a settings.json another test saved from supplying keys here."""
    monkeypatch.setenv("NIMBUS_HOME", str(tmp_path))


@pytest.fixture
def settings() -> Settings:
    # Explicit Nones, because a stray OPENAI_API_KEY in os.environ would otherwise fill these in.
    return Settings(_env_file=None, openai_api_key=None, anthropic_api_key=None, compatible_api_key=None)


def _raise(error: Exception) -> object:
    def fail(*args: object) -> None:
        raise error

    return fail


def test_save_api_key_stores_the_key_for_get_api_key(settings: Settings) -> None:
    save_api_key("openai", "sk-abc")

    assert get_api_key("openai", settings) == "sk-abc"


def test_save_api_key_strips_surrounding_whitespace(settings: Settings) -> None:
    save_api_key("anthropic", "  sk-ant \n")

    assert get_api_key("anthropic", settings) == "sk-ant"


def test_save_api_key_rejects_an_empty_key() -> None:
    with pytest.raises(SecretStoreError):
        save_api_key("openai", "   ")


def test_save_api_key_refuses_ollama() -> None:
    with pytest.raises(SecretStoreError):
        save_api_key("ollama", "anything")


def test_save_api_key_wraps_a_credential_store_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyring.set_password", _raise(KeyringError("locked")))

    with pytest.raises(SecretStoreError):
        save_api_key("openai", "sk-abc")


def test_delete_api_key_removes_a_stored_key(settings: Settings) -> None:
    save_api_key("openai", "sk-abc")

    delete_api_key("openai")

    assert get_api_key("openai", settings) is None


def test_delete_api_key_is_a_no_op_when_nothing_is_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyring.delete_password", _raise(PasswordDeleteError("not found")))

    delete_api_key("openai")


def test_delete_api_key_wraps_a_credential_store_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyring.delete_password", _raise(KeyringError("locked")))

    with pytest.raises(SecretStoreError):
        delete_api_key("openai")


def test_delete_api_key_refuses_ollama() -> None:
    with pytest.raises(SecretStoreError):
        delete_api_key("ollama")


def test_get_api_key_prefers_the_stored_key_over_dotenv() -> None:
    save_api_key("openai", "sk-stored")

    assert get_api_key("openai", Settings(_env_file=None, openai_api_key="sk-env")) == "sk-stored"


def test_get_api_key_falls_back_to_the_dotenv_field() -> None:
    assert get_api_key("anthropic", Settings(_env_file=None, anthropic_api_key="sk-env")) == "sk-env"


def test_get_api_key_maps_openai_compatible_to_the_compatible_key_field() -> None:
    settings = Settings(_env_file=None, compatible_api_key="sk-compat")

    assert get_api_key("openai_compatible", settings) == "sk-compat"


def test_get_api_key_returns_none_for_ollama(settings: Settings) -> None:
    assert get_api_key("ollama", settings) is None


def test_get_api_key_falls_back_to_dotenv_when_the_store_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("keyring.get_password", _raise(KeyringError("locked")))

    with caplog.at_level(logging.WARNING):
        key = get_api_key("openai", Settings(_env_file=None, openai_api_key="sk-env"))

    assert key == "sk-env"
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_has_api_key_is_true_once_a_key_is_saved(settings: Settings) -> None:
    save_api_key("openai", "sk-abc")

    assert has_api_key("openai", settings) is True


def test_has_api_key_is_false_with_no_key_anywhere(settings: Settings) -> None:
    assert has_api_key("anthropic", settings) is False
