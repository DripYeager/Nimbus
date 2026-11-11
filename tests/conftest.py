from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Must happen before any Nimbus module resolves a data path, so no test ever reads or writes
# the real %APPDATA%\Nimbus (saved settings, logs, the index, chats).
os.environ["NIMBUS_HOME"] = tempfile.mkdtemp(prefix="nimbus-tests-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# A dependency of the document parser loads .env into os.environ on import; keep tests clean.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import config.settings as settings_module  # noqa: E402

# Tests must not depend on whatever the developer has in their own .env.
settings_module.Settings.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Every test starts from defaults, unaffected by settings another test saved or patched."""
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture(autouse=True)
def _no_real_credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps tests out of Windows Credential Manager; secret_store tests patch keyring themselves."""
    vault: dict[tuple[str, str], str] = {}
    monkeypatch.setattr("keyring.get_password", lambda service, user: vault.get((service, user)))
    monkeypatch.setattr("keyring.set_password", lambda service, user, pw: vault.__setitem__((service, user), pw))
    monkeypatch.setattr("keyring.delete_password", lambda service, user: vault.pop((service, user), None))


@pytest.fixture(autouse=True)
def _no_reranker_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that starts the engine must never fetch the 150 MB reranker; reranker tests
    patch the model class themselves."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Tests don't download models.")

    monkeypatch.setattr("core.reranker.TextCrossEncoder", refuse)


@pytest.fixture(autouse=True)
def _no_whisper_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never fetch the speech model; transcriber tests patch the model class themselves."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Tests don't download models.")

    monkeypatch.setattr("core.transcriber.WhisperModel", refuse)
