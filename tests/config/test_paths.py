from __future__ import annotations

import sys
from pathlib import Path

import pytest

import config.paths
from config.paths import (
    app_data_dir,
    asset_path,
    is_frozen,
    log_dir,
    model_cache_dir,
    notes_dir,
    user_settings_path,
)

REPO_ROOT = Path(config.paths.__file__).resolve().parent.parent


@pytest.fixture
def no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NIMBUS_HOME", raising=False)


def test_app_data_dir_uses_the_nimbus_home_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NIMBUS_HOME", str(tmp_path))

    assert app_data_dir() == tmp_path


def test_app_data_dir_expands_a_tilde_in_the_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMBUS_HOME", "~/nimbus-dev")

    assert app_data_dir() == Path.home() / "nimbus-dev"


def test_app_data_dir_uses_roaming_appdata_on_windows(
    no_override: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert app_data_dir() == tmp_path / "Nimbus"


def test_app_data_dir_falls_back_to_a_dot_folder_off_windows(
    no_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert app_data_dir() == Path.home() / ".nimbus"


def test_app_data_dir_falls_back_to_a_dot_folder_when_appdata_is_unset(
    no_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)

    assert app_data_dir() == Path.home() / ".nimbus"


def test_user_settings_path_lives_in_the_data_dir() -> None:
    assert user_settings_path() == app_data_dir() / "settings.json"


def test_log_notes_and_model_dirs_live_in_the_data_dir() -> None:
    assert [log_dir(), notes_dir(), model_cache_dir()] == [
        app_data_dir() / "logs",
        app_data_dir() / "notes",
        app_data_dir() / "models",
    ]


def test_is_frozen_is_false_when_running_from_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert is_frozen() is False


def test_is_frozen_is_true_inside_a_packaged_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert is_frozen() is True


def test_asset_path_points_into_the_source_tree_when_running_from_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert asset_path("icons", "check.svg") == REPO_ROOT / "assets" / "icons" / "check.svg"


def test_asset_path_finds_a_bundled_file_when_running_from_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert asset_path("fonts", "Bangers-Regular.ttf").is_file()


def test_asset_path_points_into_the_unpacked_bundle_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert asset_path("icons", "check.svg") == tmp_path / "assets" / "icons" / "check.svg"


def test_asset_path_with_no_parts_is_the_assets_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert asset_path() == REPO_ROOT / "assets"
