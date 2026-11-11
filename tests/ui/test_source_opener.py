from __future__ import annotations

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QUrl
from pytest_mock import MockerFixture

from ui.source_opener import default_app_for, open_source, page_command

PDF = "C:/Docs/Vendor Agreement.pdf"


@pytest.fixture
def open_url(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.source_opener.QDesktopServices.openUrl")


@pytest.fixture
def popen(mocker: MockerFixture) -> Mock:
    return mocker.patch("ui.source_opener.subprocess.Popen")


def test_page_command_gives_a_browser_a_page_fragment() -> None:
    command = page_command("C:/Edge/msedge.exe", PDF, 12)

    assert command == ["C:/Edge/msedge.exe", f"{QUrl.fromLocalFile(PDF).toString()}#page=12"]


def test_page_command_uses_acrobats_open_action() -> None:
    assert page_command("C:/Adobe/Acrobat.exe", PDF, 4) == ["C:/Adobe/Acrobat.exe", "/A", "page=4", PDF]


def test_page_command_uses_sumatras_page_flag() -> None:
    assert page_command("C:/S/SumatraPDF.exe", PDF, 7) == ["C:/S/SumatraPDF.exe", "-page", "7", PDF]


@pytest.mark.parametrize("app", [None, "C:/Other/viewer.exe"])
def test_page_command_is_none_for_unknown_apps(app: str | None) -> None:
    assert page_command(app, PDF, 2) is None


def test_open_source_launches_the_pdf_app_at_the_page(mocker: MockerFixture, popen: Mock, open_url: Mock) -> None:
    mocker.patch("ui.source_opener.default_app_for", return_value="C:/S/SumatraPDF.exe")

    open_source(PDF, 5)

    popen.assert_called_once()
    open_url.assert_not_called()


def test_open_source_falls_back_when_the_app_has_no_page_option(
    mocker: MockerFixture, popen: Mock, open_url: Mock
) -> None:
    mocker.patch("ui.source_opener.default_app_for", return_value="C:/Other/viewer.exe")

    open_source(PDF, 5)

    popen.assert_not_called()
    open_url.assert_called_once_with(QUrl.fromLocalFile(PDF))


def test_open_source_falls_back_when_launching_fails(mocker: MockerFixture, popen: Mock, open_url: Mock) -> None:
    mocker.patch("ui.source_opener.default_app_for", return_value="C:/Edge/msedge.exe")
    popen.side_effect = OSError("gone")

    open_source(PDF, 5)

    open_url.assert_called_once()


def test_open_source_opens_other_files_normally(popen: Mock, open_url: Mock) -> None:
    open_source("C:/Docs/notes.docx", 2)

    popen.assert_not_called()
    open_url.assert_called_once_with(QUrl.fromLocalFile("C:/Docs/notes.docx"))


def test_default_app_for_finds_a_program_or_nothing() -> None:
    app = default_app_for(".txt")

    assert app is None or app.lower().endswith(".exe")
