from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tools.create_toolbox import CreateToolbox
from tools.registry import ToolRegistry


@pytest.fixture
def home(tmp_path: Path, mocker: MockerFixture) -> Path:
    folder = tmp_path / "home"
    (folder / "Downloads").mkdir(parents=True)
    mocker.patch("tools.create_toolbox.Path.home", return_value=folder)
    return folder


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    folder = tmp_path / "Work"
    (folder / "Reports").mkdir(parents=True)
    return folder


@pytest.fixture
def toolbox(tmp_path: Path, shared: Path) -> CreateToolbox:
    return CreateToolbox(lambda: [shared], output_dir=tmp_path / "Documents" / "Nimbus")


def test_folder_for_uses_documents_nimbus_when_none_is_asked(toolbox: CreateToolbox, tmp_path: Path) -> None:
    assert toolbox.folder_for("") == tmp_path / "Documents" / "Nimbus"


def test_folder_for_uses_a_full_path_as_given(toolbox: CreateToolbox, tmp_path: Path) -> None:
    assert toolbox.folder_for(str(tmp_path / "Projects" / "Q3")) == (tmp_path / "Projects" / "Q3").resolve()


def test_folder_for_finds_a_name_in_the_home_folder(toolbox: CreateToolbox, home: Path) -> None:
    assert toolbox.folder_for("Downloads") == (home / "Downloads").resolve()


def test_folder_for_finds_a_name_inside_a_shared_folder(toolbox: CreateToolbox, home: Path, shared: Path) -> None:
    assert toolbox.folder_for("Reports") == (shared / "Reports").resolve()


def test_folder_for_creates_an_unknown_name_under_home(toolbox: CreateToolbox, home: Path) -> None:
    assert toolbox.folder_for("Trips") == (home / "Trips").resolve()


def test_create_document_saves_in_the_asked_folder(toolbox: CreateToolbox, home: Path) -> None:
    result = toolbox.create_document({"file_name": "plan.docx", "content": "# Plan", "folder": "Downloads"})

    assert (home / "Downloads" / "plan.docx").exists()
    assert [s.file_name for s in result.sources] == ["plan.docx"]


def test_create_spreadsheet_reports_its_rows(toolbox: CreateToolbox, tmp_path: Path) -> None:
    result = toolbox.create_spreadsheet({"file_name": "budget.xlsx", "csv": "Item,Cost\nHotel,10\nCar,5"})

    assert "with 2 rows" in result.content
    assert (tmp_path / "Documents" / "Nimbus" / "budget.xlsx").exists()


def test_describe_shows_the_exact_folder_on_the_approval_card(toolbox: CreateToolbox, home: Path) -> None:
    text = toolbox.describe({"file_name": "plan.docx", "folder": "Downloads"})

    assert text == f"Create “plan.docx” in {(home / 'Downloads').resolve()}"


def test_register_adds_both_tools_behind_approval(toolbox: CreateToolbox) -> None:
    registry = ToolRegistry()

    toolbox.register(registry)

    tools = [registry.get(name) for name in ("create_document", "create_spreadsheet")]
    assert all(tool is not None and tool.requires_confirmation for tool in tools)
