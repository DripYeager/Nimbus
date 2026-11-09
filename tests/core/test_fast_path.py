from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import AppLaunchError, ToolError
from core.fast_path import CONFIDENT_APP_SCORE, FastPath
from core.file_catalog import FileCatalog
from models.schema import AppEntry, CatalogMatch, SourceRef
from tools.action_toolbox import ActionToolbox

SPOTIFY = AppEntry(name="Spotify", launch_target="C:/Spotify.lnk", source="start_menu")


def _match(path: str, score: float) -> CatalogMatch:
    return CatalogMatch(
        file_path=path, file_name=Path(path).name, size_bytes=100, modified_at=datetime(2026, 1, 1), score=score
    )


@pytest.fixture
def catalog(mocker: MockerFixture) -> Mock:
    catalog = mocker.Mock(spec=FileCatalog)
    catalog.search_names.return_value = []
    return catalog


@pytest.fixture
def actions(mocker: MockerFixture) -> Mock:
    actions = mocker.Mock(spec=ActionToolbox)
    actions.best_app_match.return_value = None
    return actions


@pytest.fixture
def launch(mocker: MockerFixture) -> Mock:
    return mocker.patch("core.fast_path.launch_app")


@pytest.fixture
def open_path(mocker: MockerFixture) -> Mock:
    return mocker.patch("core.fast_path.open_path")


@pytest.fixture
def fast_path(catalog: Mock, actions: Mock) -> FastPath:
    return FastPath(catalog, actions)


def test_try_answer_launches_a_confidently_matched_app(fast_path: FastPath, actions: Mock, launch: Mock) -> None:
    actions.best_app_match.return_value = SPOTIFY

    answer = fast_path.try_answer("open spotify")

    launch.assert_called_once_with(SPOTIFY)
    assert answer.text == "Opening **Spotify**."


def test_try_answer_asks_for_an_app_match_at_the_confident_score(fast_path: FastPath, actions: Mock) -> None:
    fast_path.try_answer("please launch my spotify!")

    actions.best_app_match.assert_called_once_with("spotify", min_score=CONFIDENT_APP_SCORE)


def test_try_answer_falls_through_without_a_confident_app(fast_path: FastPath, launch: Mock) -> None:
    assert fast_path.try_answer("open spotfy") is None
    launch.assert_not_called()


def test_try_answer_falls_through_for_a_described_file(
    fast_path: FastPath, catalog: Mock, launch: Mock, open_path: Mock
) -> None:
    assert fast_path.try_answer("open the invoice pdf") is None
    catalog.search_names.assert_not_called()
    launch.assert_not_called()


def test_try_answer_reports_an_app_that_would_not_start(fast_path: FastPath, actions: Mock, launch: Mock) -> None:
    actions.best_app_match.return_value = SPOTIFY
    launch.side_effect = AppLaunchError("it was uninstalled")

    answer = fast_path.try_answer("open spotify")

    assert "couldn't start it: it was uninstalled" in answer.text


def test_try_answer_opens_a_confidently_matched_file(fast_path: FastPath, catalog: Mock, open_path: Mock) -> None:
    catalog.search_names.return_value = [_match("C:/Docs/report.pdf", 97)]

    answer = fast_path.try_answer("open report.pdf")

    open_path.assert_called_once_with(Path("C:/Docs/report.pdf"))
    assert answer.sources == [SourceRef(file_name="report.pdf", file_path="C:/Docs/report.pdf", score=97)]


def test_try_answer_falls_through_for_a_weak_file_match(fast_path: FastPath, catalog: Mock, open_path: Mock) -> None:
    catalog.search_names.return_value = [_match("C:/Docs/rapport.pdf", 70)]

    assert fast_path.try_answer("open report.pdf") is None
    open_path.assert_not_called()


def test_try_answer_reports_a_file_that_would_not_open(fast_path: FastPath, catalog: Mock, open_path: Mock) -> None:
    catalog.search_names.return_value = [_match("C:/Docs/report.pdf", 97)]
    open_path.side_effect = ToolError("no app for .pdf")

    answer = fast_path.try_answer("open report.pdf")

    assert "couldn't open it: no app for .pdf" in answer.text


def test_try_answer_lists_files_for_a_find_command(fast_path: FastPath, catalog: Mock) -> None:
    catalog.search_names.return_value = [_match("C:/Docs/report.pdf", 98), _match("C:/Old/report.pdf", 92)]

    answer = fast_path.try_answer("find report.pdf")

    assert "**report.pdf**" in answer.text
    assert [s.file_path for s in answer.sources] == ["C:/Docs/report.pdf", "C:/Old/report.pdf"]


def test_try_answer_falls_through_when_the_best_found_file_is_weak(fast_path: FastPath, catalog: Mock) -> None:
    catalog.search_names.return_value = [_match("C:/Docs/rapport.pdf", 60)]

    assert fast_path.try_answer("where is report.pdf?") is None


def test_try_answer_falls_through_for_a_find_without_a_file_name(fast_path: FastPath, catalog: Mock) -> None:
    assert fast_path.try_answer("find my tax documents") is None
    catalog.search_names.assert_not_called()


def test_try_answer_falls_through_for_a_compound_request(fast_path: FastPath, actions: Mock, launch: Mock) -> None:
    actions.best_app_match.return_value = SPOTIFY

    assert fast_path.try_answer("open spotify and play some jazz") is None
    launch.assert_not_called()


def test_try_answer_falls_through_for_a_question(fast_path: FastPath, actions: Mock) -> None:
    assert fast_path.try_answer("what did the contract say about notice periods?") is None
    actions.best_app_match.assert_not_called()
