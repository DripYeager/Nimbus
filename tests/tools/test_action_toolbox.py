from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from models.schema import AppEntry
from models.system import NoteMatch, SystemStatus
from tools.action_toolbox import ActionToolbox
from tools.app_catalog import AppCatalog
from tools.registry import ToolRegistry

ACTION_TOOLS = {"open_app", "open_file", "reveal_in_explorer", "open_website", "open_windows_setting", "save_note"}


def _app(name: str, source: str = "registry") -> AppEntry:
    return AppEntry(name=name, launch_target=f"C:/{name}.exe", source=source)


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "report.pdf").write_bytes(b"%PDF")
    return folder.resolve()


@pytest.fixture
def apps(mocker: MockerFixture) -> Mock:
    apps = mocker.Mock(spec=AppCatalog)
    apps.find.return_value = []
    return apps


@pytest.fixture
def toolbox(apps: Mock, shared: Path) -> ActionToolbox:
    return ActionToolbox(apps, lambda path: shared in path.parents)


@pytest.fixture
def launch(mocker: MockerFixture) -> Mock:
    return mocker.patch("tools.action_toolbox.launch_app")


@pytest.fixture
def open_path(mocker: MockerFixture) -> Mock:
    return mocker.patch("tools.action_toolbox.open_path")


def test_register_marks_every_action_tool_as_needing_confirmation(toolbox: ActionToolbox) -> None:
    registry = ToolRegistry()

    toolbox.register(registry)

    needing = {name for name in registry.names() if registry.get(name).requires_confirmation}
    assert needing == ACTION_TOOLS


def test_register_leaves_read_only_tools_unconfirmed(toolbox: ActionToolbox) -> None:
    registry = ToolRegistry()

    toolbox.register(registry)

    assert set(registry.names()) - ACTION_TOOLS == {"search_notes", "system_status"}


def test_best_app_match_prefers_start_menu_on_a_tie(toolbox: ActionToolbox, apps: Mock) -> None:
    shortcut = _app("Google Chrome", "start_menu")
    apps.find.return_value = [(_app("chrome"), 90.0), (shortcut, 90.0)]

    assert toolbox.best_app_match("chrome") == shortcut


def test_best_app_match_keeps_a_clearly_better_registry_match(toolbox: ActionToolbox, apps: Mock) -> None:
    exact = _app("Spotify")
    apps.find.return_value = [(exact, 100.0), (_app("Spotify Helper", "start_menu"), 80.0)]

    assert toolbox.best_app_match("spotify") == exact


def test_best_app_match_returns_none_below_the_default_minimum(toolbox: ActionToolbox, apps: Mock) -> None:
    apps.find.return_value = [(_app("Notepad"), 60.0)]

    assert toolbox.best_app_match("spotify") is None


def test_best_app_match_respects_a_custom_min_score(toolbox: ActionToolbox, apps: Mock) -> None:
    apps.find.return_value = [(_app("Spotify"), 85.0)]

    assert toolbox.best_app_match("spotify", min_score=90.0) is None


def test_best_app_match_returns_none_for_an_empty_catalog(toolbox: ActionToolbox) -> None:
    assert toolbox.best_app_match("spotify") is None


def test_open_app_launches_the_best_match(toolbox: ActionToolbox, apps: Mock, launch: Mock) -> None:
    spotify = _app("Spotify", "start_menu")
    apps.find.return_value = [(spotify, 100.0)]

    result = toolbox.open_app({"name": "spotify"})

    launch.assert_called_once_with(spotify)
    assert result.content == "Opened Spotify."


def test_open_app_raises_when_no_app_matches(toolbox: ActionToolbox, launch: Mock) -> None:
    with pytest.raises(ToolError, match="No installed app"):
        toolbox.open_app({"name": "spotify"})

    launch.assert_not_called()


def test_open_file_opens_a_shared_file(toolbox: ActionToolbox, shared: Path, open_path: Mock) -> None:
    result = toolbox.open_file({"path": str(shared / "report.pdf")})

    open_path.assert_called_once_with(shared / "report.pdf")
    assert result.sources[0].file_name == "report.pdf"


def test_open_file_refuses_a_path_outside_the_shared_folders(
    toolbox: ActionToolbox, tmp_path: Path, open_path: Mock
) -> None:
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(ToolError, match="outside the folders"):
        toolbox.open_file({"path": str(outside)})

    open_path.assert_not_called()


def test_open_file_refuses_parent_traversal(toolbox: ActionToolbox, shared: Path, open_path: Mock) -> None:
    with pytest.raises(ToolError, match="outside the folders"):
        toolbox.open_file({"path": str(shared / ".." / "shared-not" / "x.txt")})


def test_open_file_raises_for_a_missing_file(toolbox: ActionToolbox, shared: Path, open_path: Mock) -> None:
    with pytest.raises(ToolError, match="doesn't exist"):
        toolbox.open_file({"path": str(shared / "gone.pdf")})


def test_reveal_file_shows_a_shared_file(toolbox: ActionToolbox, shared: Path, mocker: MockerFixture) -> None:
    reveal = mocker.patch("tools.action_toolbox.reveal_in_explorer")

    toolbox.reveal_file({"path": str(shared / "report.pdf")})

    reveal.assert_called_once_with(shared / "report.pdf")


def test_open_website_opens_the_url(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    open_url = mocker.patch("tools.action_toolbox.open_url")

    result = toolbox.open_website({"url": "https://example.com"})

    open_url.assert_called_once_with("https://example.com")
    assert "https://example.com" in result.content


def test_open_website_propagates_a_rejected_url(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    mocker.patch("tools.action_toolbox.open_url", side_effect=ToolError("only http"))

    with pytest.raises(ToolError):
        toolbox.open_website({"url": "file:///C:/x"})


def test_open_setting_reports_the_page_it_opened(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    mocker.patch("tools.action_toolbox.open_windows_setting", return_value="bluetooth")

    assert toolbox.open_setting({"page": "Bluetooth settings"}).content == "Opened Windows Settings → bluetooth."


def test_system_status_returns_the_snapshot_as_json(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    status = SystemStatus(
        disk_free_gb=10, disk_total_gb=100, cpu_percent=5, memory_percent=40, local_time="09:00", uptime_hours=2
    )
    mocker.patch("tools.action_toolbox.read_system_status", return_value=status)

    assert SystemStatus.model_validate_json(toolbox.system_status({}).content) == status


def test_write_note_saves_and_links_the_note(toolbox: ActionToolbox, tmp_path: Path, mocker: MockerFixture) -> None:
    save = mocker.patch("tools.action_toolbox.save_note", return_value=tmp_path / "2026_groceries.md")

    result = toolbox.write_note({"title": "Groceries", "body": "milk"})

    save.assert_called_once_with("Groceries", "milk")
    assert result.content == "Saved the note as 2026_groceries.md."


def test_find_notes_lists_matching_notes(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    note = NoteMatch(path="C:/notes/groceries.md", title="Groceries", modified_at=datetime(2026, 11, 1), preview="milk")
    mocker.patch("tools.action_toolbox.search_notes", return_value=[note])

    result = toolbox.find_notes({"query": "milk"})

    assert result.content == "- Groceries (2026-11-01): milk"
    assert result.sources[0].file_name == "groceries.md"


def test_find_notes_says_so_when_nothing_matches(toolbox: ActionToolbox, mocker: MockerFixture) -> None:
    mocker.patch("tools.action_toolbox.search_notes", return_value=[])

    assert toolbox.find_notes({}).content == "No saved notes match that."
