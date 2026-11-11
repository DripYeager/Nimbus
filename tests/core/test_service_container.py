from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from config.settings import get_settings
from config.settings_store import save_user_settings
from core.api_auth import BRIDGE_TOKEN_FILE
from core.exceptions import ProviderError
from core.service_container import AppServices, _remove_legacy_index


@pytest.fixture
def services(mocker: MockerFixture) -> AppServices:
    built = AppServices()
    built.index = mocker.Mock()
    built.watcher = mocker.Mock()
    built.provider = mocker.Mock()
    return built


def test_apply_settings_still_applies_folders_and_listeners_when_the_provider_refuses(
    services: AppServices, mocker: MockerFixture
) -> None:
    listener = mocker.Mock()
    services.add_settings_listener(listener)
    services.provider.reload.side_effect = ProviderError("needs a base URL")

    with pytest.raises(ProviderError):
        services.apply_settings()

    services.index.apply_settings.assert_called_once()
    services.watcher.restart.assert_called_once()
    listener.assert_called_once()


def test_is_path_shared_accepts_a_path_inside_a_source(services: AppServices, tmp_path: Path) -> None:
    services.index.rules.is_covered.return_value = True

    assert services.is_path_shared(tmp_path / "report.pdf")


def test_is_path_shared_rejects_a_path_outside_every_source(services: AppServices, tmp_path: Path) -> None:
    services.index.rules.is_covered.return_value = False

    assert not services.is_path_shared(tmp_path / "secret.txt")


def test_remove_legacy_index_deletes_the_old_lancedb_folder(tmp_path: Path) -> None:
    old = tmp_path / "index"
    (old / "chunks.lance").mkdir(parents=True)

    _remove_legacy_index(old)

    assert not old.exists()


def test_remove_legacy_index_leaves_an_unrelated_folder_alone(tmp_path: Path) -> None:
    folder = tmp_path / "index"
    folder.mkdir()
    (folder / "my-notes.txt").write_text("keep me", encoding="utf-8")

    _remove_legacy_index(folder)

    assert (folder / "my-notes.txt").exists()


def test_apply_settings_writes_bridge_token_only_while_sharing(services: AppServices, mocker: MockerFixture) -> None:
    services.mcp = mocker.Mock()
    token_file = get_settings().data_dir / BRIDGE_TOKEN_FILE
    save_user_settings({"share_with_mcp_apps": True})
    services.apply_settings()
    assert token_file.exists()

    save_user_settings({"share_with_mcp_apps": False})
    services.apply_settings()

    assert not token_file.exists()
    services.mcp.start.assert_called_with([])
