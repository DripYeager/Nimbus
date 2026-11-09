from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from models.schema import AppEntry
from tools import app_catalog
from tools.app_catalog import APP_PATHS_KEY, AppCatalog, build_app_catalog

HKCU, HKLM = 1, 2


@pytest.fixture
def start_menu(tmp_path: Path, mocker: MockerFixture) -> Path:
    folder = tmp_path / "Programs"
    folder.mkdir()
    mocker.patch("tools.app_catalog._start_menu_dirs", return_value=[folder, tmp_path / "missing"])
    return folder


@pytest.fixture
def store_apps(mocker: MockerFixture) -> MagicMock:
    run = mocker.patch("tools.app_catalog.subprocess.run")
    run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="")
    return run


@pytest.fixture
def registry(mocker: MockerFixture) -> dict[str, str]:
    """A fake winreg whose App Paths key holds whatever the test puts in the returned dict."""
    subkeys: dict[str, str] = {}
    fake = mocker.patch("tools.app_catalog.winreg")
    fake.HKEY_CURRENT_USER, fake.HKEY_LOCAL_MACHINE = HKCU, HKLM

    def open_key(parent: object, name: str, *_: object) -> MagicMock:
        handle = MagicMock()
        handle.__enter__.return_value = name
        return handle

    fake.OpenKey.side_effect = open_key
    fake.QueryInfoKey.side_effect = lambda _: (len(subkeys), 0, 0)
    fake.EnumKey.side_effect = lambda _, index: list(subkeys)[index]
    fake.QueryValueEx.side_effect = lambda key, _: (subkeys[key], 1)
    return subkeys


def _store_json(*apps: tuple[str, str]) -> str:
    return json.dumps([{"Name": name, "AppID": app_id} for name, app_id in apps])


def test_build_app_catalog_finds_start_menu_shortcuts(start_menu: Path, store_apps: MagicMock, registry: dict) -> None:
    (start_menu / "Tools").mkdir()
    (start_menu / "Tools" / "Notepad++.lnk").touch()
    (start_menu / "Docs.url").touch()
    (start_menu / "ignored.txt").touch()
    names = {entry.name for entry in build_app_catalog()}
    assert names == {"Notepad++", "Docs"}


def test_build_app_catalog_skips_uninstallers_and_readmes(
    start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    for name in ("Uninstall Foo", "Foo Readme", "Foo Website", "Foo"):
        (start_menu / f"{name}.lnk").touch()
    assert [entry.name for entry in build_app_catalog()] == ["Foo"]


def test_build_app_catalog_reads_store_apps(start_menu: Path, store_apps: MagicMock, registry: dict) -> None:
    store_apps.return_value.stdout = _store_json(("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"))
    catalog = build_app_catalog()
    assert catalog == [
        AppEntry(name="Calculator", launch_target="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", source="store_app")
    ]


def test_build_app_catalog_accepts_single_store_app_object(
    start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    store_apps.return_value.stdout = json.dumps({"Name": "Photos", "AppID": "Microsoft.Photos!App"})
    assert [entry.name for entry in build_app_catalog()] == ["Photos"]


def test_build_app_catalog_tolerates_powershell_timeout(
    start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    (start_menu / "Foo.lnk").touch()
    store_apps.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=15)
    assert [entry.name for entry in build_app_catalog()] == ["Foo"]


def test_build_app_catalog_tolerates_non_json_store_output(
    start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    store_apps.return_value.stdout = "Get-StartApps : The term is not recognized"
    assert build_app_catalog() == []


def test_build_app_catalog_reads_app_paths_and_strips_exe(
    tmp_path: Path, start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    exe = tmp_path / "chrome.exe"
    exe.touch()
    registry["chrome.exe"] = f'"{exe}"'
    registry["gone.exe"] = str(tmp_path / "gone.exe")
    catalog = build_app_catalog()
    assert catalog == [AppEntry(name="chrome", launch_target=str(exe), source="registry")]


def test_build_app_catalog_tolerates_unreadable_hive(
    tmp_path: Path, start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    exe = tmp_path / "tool.exe"
    exe.touch()
    registry["tool.exe"] = str(exe)
    fake = app_catalog.winreg.OpenKey
    allowed = fake.side_effect

    def deny_machine_hive(parent: object, name: str, *args: object) -> MagicMock:
        if parent == HKLM and name == APP_PATHS_KEY:
            raise PermissionError("Access is denied")
        return allowed(parent, name, *args)

    fake.side_effect = deny_machine_hive
    assert [entry.name for entry in build_app_catalog()] == ["tool"]


def test_build_app_catalog_prefers_start_menu_over_store_and_registry(
    tmp_path: Path, start_menu: Path, store_apps: MagicMock, registry: dict
) -> None:
    (start_menu / "Spotify.lnk").touch()
    exe = tmp_path / "spotify.exe"
    exe.touch()
    registry["Spotify.exe"] = str(exe)
    store_apps.return_value.stdout = _store_json(("SPOTIFY", "SpotifyAB.Spotify!App"), ("Teams", "MSTeams!App"))
    exe_teams = tmp_path / "teams.exe"
    exe_teams.touch()
    registry["teams.exe"] = str(exe_teams)
    sources = {entry.name.lower(): entry.source for entry in build_app_catalog()}
    assert sources == {"spotify": "start_menu", "teams": "store_app"}


def _entries(*names: str) -> list[AppEntry]:
    return [AppEntry(name=name, launch_target=f"C:/{name}.lnk", source="start_menu") for name in names]


def _write_cache(path: Path, entries: list[AppEntry], age: timedelta) -> None:
    built_at = (datetime.now(UTC) - age).isoformat()
    path.write_text(json.dumps({"built_at": built_at, "entries": [e.model_dump() for e in entries]}), encoding="utf-8")


def test_load_or_build_uses_fresh_cache(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = tmp_path / "app_catalog.json"
    _write_cache(cache, _entries("Word"), age=timedelta(days=1))
    build = mocker.patch("tools.app_catalog.build_app_catalog")
    catalog = AppCatalog(cache)
    catalog.load_or_build()
    build.assert_not_called()
    assert [e.name for e in catalog.entries()] == ["Word"]


def test_load_or_build_rebuilds_stale_cache(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = tmp_path / "app_catalog.json"
    _write_cache(cache, _entries("Old"), age=timedelta(days=8))
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("New"))
    catalog = AppCatalog(cache)
    catalog.load_or_build()
    assert [e.name for e in catalog.entries()] == ["New"]


def test_load_or_build_rebuilds_corrupt_cache(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = tmp_path / "app_catalog.json"
    cache.write_text("{not json", encoding="utf-8")
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("New"))
    catalog = AppCatalog(cache)
    catalog.load_or_build()
    assert [e.name for e in catalog.entries()] == ["New"]


def test_refresh_saves_cache_that_load_can_read(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = tmp_path / "nested" / "app_catalog.json"
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("Excel"))
    AppCatalog(cache).refresh()
    reloaded = AppCatalog(cache)
    mocker.patch("tools.app_catalog.build_app_catalog", side_effect=AssertionError("cache should be used"))
    reloaded.load_or_build()
    assert [e.name for e in reloaded.entries()] == ["Excel"]


def test_refresh_keeps_entries_when_cache_write_fails(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("Excel"))
    mocker.patch.object(Path, "write_text", side_effect=PermissionError("read-only"))
    catalog = AppCatalog(tmp_path / "app_catalog.json")
    catalog.refresh()
    assert catalog.is_ready()
    assert [e.name for e in catalog.entries()] == ["Excel"]


def test_is_ready_false_before_first_load(tmp_path: Path) -> None:
    assert AppCatalog(tmp_path / "app_catalog.json").is_ready() is False


def test_find_ranks_best_match_first(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("Visual Studio Code", "Spotify", "Paint"))
    catalog = AppCatalog(tmp_path / "app_catalog.json")
    catalog.refresh()
    results = catalog.find("spotify", limit=2)
    assert results[0][0].name == "Spotify"
    assert results[0][1] == pytest.approx(100.0)
    assert len(results) == 2


def test_find_returns_empty_before_catalog_loads(tmp_path: Path) -> None:
    assert AppCatalog(tmp_path / "app_catalog.json").find("spotify") == []


def test_find_returns_empty_for_blank_query(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("tools.app_catalog.build_app_catalog", return_value=_entries("Spotify"))
    catalog = AppCatalog(tmp_path / "app_catalog.json")
    catalog.refresh()
    assert catalog.find("   ") == []
