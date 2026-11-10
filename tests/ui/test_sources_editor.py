from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from models.schema import FileCategory, IndexStatus, SourceSummary
from ui.api_client import ApiClient
from ui.settings.source_row import SourceRow
from ui.settings.sources_editor import SourcesEditor, describe_source_counts

VALUES: dict[str, Any] = {
    "sources": [
        {"path": "C:/Users/me/Documents", "include_contents": True},
        {"path": "D:/Media", "include_contents": False},
    ],
    "file_categories": ["pdfs", "code"],
    "max_file_size_mb": 120,
    "exclude_patterns": ["*.iso", "Archive"],
}


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    ok(fn())


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=ApiClient)
    fake.source_summaries.return_value = [
        SourceSummary(
            path="C:/Users/me/Documents", include_contents=True, exists=True, file_count=1240, indexed_count=980
        )
    ]
    fake.index_status.return_value = IndexStatus(content_files=5600, indexed_files=1240, failed_files=3)
    mocker.patch("ui.settings.sources_editor.run_in_background", side_effect=_synchronous)
    mocker.patch("ui.settings.index_panel.run_in_background", side_effect=_synchronous)
    return fake


def test_collect_round_trips_loaded_values(api: Mock) -> None:
    editor = SourcesEditor(api)
    editor.load(VALUES)
    assert editor.collect() == VALUES


def test_load_shows_folder_counts(api: Mock) -> None:
    editor = SourcesEditor(api)
    editor.load(VALUES)
    assert editor._rows[0].counts_label.text() == "1,240 files · all read"


def test_choose_folder_adds_new_folder(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.sources_editor.QFileDialog.getExistingDirectory", return_value="E:/Projects")
    editor = SourcesEditor(api)
    editor.load(VALUES)
    editor._choose_folder()
    assert editor.collect()["sources"][-1] == {"path": "E:\\Projects", "include_contents": True}


def test_choose_folder_ignores_duplicate(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.sources_editor.QFileDialog.getExistingDirectory", return_value="d:/media")
    editor = SourcesEditor(api)
    editor.load(VALUES)
    editor._choose_folder()
    assert len(editor.collect()["sources"]) == 2


def test_remove_row_drops_folder(api: Mock) -> None:
    editor = SourcesEditor(api)
    editor.load(VALUES)
    editor._remove_row(editor._rows[0])
    assert editor.collect()["sources"] == [{"path": "D:/Media", "include_contents": False}]


def test_describe_source_counts_reports_missing_folder() -> None:
    summary = SourceSummary(path="X:/gone", include_contents=True, exists=False, file_count=0, indexed_count=0)
    assert describe_source_counts(summary) == "Folder not found"


def test_describe_source_counts_marks_a_names_only_folder() -> None:
    summary = SourceSummary(path="D:/Media", include_contents=False, exists=True, file_count=12, indexed_count=0)
    assert describe_source_counts(summary) == "12 files · names only"


def _progress(**fields: object) -> SourceSummary:
    base = {"path": "C:/Docs", "include_contents": True, "exists": True, "file_count": 100, "indexed_count": 40}
    return SourceSummary(**{**base, **fields})


def test_describe_source_counts_names_the_file_being_read() -> None:
    summary = _progress(pending_count=60, is_active=True, current_file="report.pdf")
    assert describe_source_counts(summary) == "Reading report.pdf… · 40 of 100 read"


def test_describe_source_counts_shows_what_is_still_waiting() -> None:
    assert describe_source_counts(_progress(pending_count=60)) == "40 of 100 read · 60 waiting"


def test_describe_source_counts_mentions_files_that_failed() -> None:
    summary = _progress(indexed_count=98, failed_count=2)
    assert describe_source_counts(summary) == "100 files · all read · 2 couldn't be read"


def test_source_row_shows_progress_and_orb_for_the_active_folder() -> None:
    row = SourceRow("C:/Docs", include_contents=True)

    row.set_summary(_progress(pending_count=60, is_active=True, current_file="report.pdf"))

    assert not row.progress.isHidden()
    assert row.progress.value() == 400
    assert not row.orb.isHidden()


def test_source_row_hides_progress_once_the_folder_is_done() -> None:
    row = SourceRow("C:/Docs", include_contents=True)
    row.set_summary(_progress(pending_count=60, is_active=True, current_file="a.pdf"))

    row.set_summary(_progress(indexed_count=100))

    assert row.progress.isHidden()
    assert row.orb.isHidden()


def test_refresh_progress_skips_while_a_fetch_is_running(mocker: MockerFixture, api: Mock) -> None:
    background = mocker.patch("ui.settings.sources_editor.run_in_background")
    editor = SourcesEditor(api)

    editor.refresh_progress()
    editor.refresh_progress()

    background.assert_called_once()


def test_progress_polling_runs_only_while_shown(api: Mock) -> None:
    editor = SourcesEditor(api)

    editor.show()
    shown = editor._progress_timer.isActive()
    editor.hide()

    assert (shown, editor._progress_timer.isActive()) == (True, False)


def test_sources_editor_with_index_controls_has_panel(api: Mock) -> None:
    assert SourcesEditor(api, show_index_controls=True)._index_panel is not None


def test_collect_reflects_toggled_chip(api: Mock) -> None:
    editor = SourcesEditor(api)
    editor.load(VALUES)
    editor._category_chips[FileCategory.EMAIL].click()
    assert editor.collect()["file_categories"] == ["pdfs", "code", "email"]


def test_remove_row_shows_empty_note_when_last_folder_goes(api: Mock) -> None:
    editor = SourcesEditor(api)
    editor.load({**VALUES, "sources": [VALUES["sources"][0]]})
    editor._remove_row(editor._rows[0])
    assert not editor._empty_label.isHidden()
