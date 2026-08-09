from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pytest_mock import MockerFixture

from llm.provider import LLMProvider
from models.schema import FileMetadata
from tools.summary_tools import (
    NOTHING_TO_SUMMARIZE_MESSAGE,
    SAFE_PROMPT_WORD_LIMIT,
    summarize_document,
    summarize_todays_downloads,
)


def _file(path: str, modified_at: datetime = datetime(2026, 8, 9, 9, 0)) -> FileMetadata:
    return FileMetadata(file_path=path, file_name=Path(path).name, size_bytes=10, created_at=modified_at,
                         modified_at=modified_at)


def test_summarize_document_makes_one_call_for_a_small_document(mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.extract_document_text", return_value="A short document about invoices.")
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "five bullet points"

    result = summarize_document(Path("invoice.txt"), provider)

    assert result == "five bullet points"
    provider.complete.assert_called_once()
    assert "A short document about invoices." in provider.complete.call_args[0][0]


def test_summarize_document_map_reduces_a_large_document(mocker: MockerFixture) -> None:
    huge_text = "word " * (SAFE_PROMPT_WORD_LIMIT * 2 + 1000)
    mocker.patch("tools.summary_tools.extract_document_text", return_value=huge_text)
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.side_effect = ["part one summary", "part two summary", "part three summary", "final summary"]

    result = summarize_document(Path("big.txt"), provider)

    assert result == "final summary"
    assert provider.complete.call_count == 4
    final_prompt = provider.complete.call_args_list[-1][0][0]
    assert "part one summary" in final_prompt
    assert "part three summary" in final_prompt


def test_summarize_document_skips_the_llm_when_no_text_is_extracted(mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.extract_document_text", return_value="   ")
    provider = mocker.Mock(spec=LLMProvider)

    result = summarize_document(Path("blank.txt"), provider)

    assert result == NOTHING_TO_SUMMARIZE_MESSAGE
    provider.complete.assert_not_called()


def test_summarize_todays_downloads_reports_when_downloads_is_not_watched(mocker: MockerFixture) -> None:
    mocker.patch("tools.summary_tools.get_settings", return_value=SimpleNamespace(watched_dirs=[Path("~/Documents")]))
    provider = mocker.Mock(spec=LLMProvider)

    result = summarize_todays_downloads(provider)

    assert "isn't one of the watched folders" in result
    provider.complete.assert_not_called()


def test_summarize_todays_downloads_reports_when_nothing_was_downloaded(mocker: MockerFixture) -> None:
    mocker.patch(
        "tools.summary_tools.get_settings", return_value=SimpleNamespace(watched_dirs=[Path("~/Downloads")])
    )
    mocker.patch("tools.summary_tools.list_recent", return_value=[])
    provider = mocker.Mock(spec=LLMProvider)

    result = summarize_todays_downloads(provider)

    assert result == "No files were downloaded today."
    provider.complete.assert_not_called()


def test_summarize_todays_downloads_combines_files_into_a_single_call(mocker: MockerFixture) -> None:
    mocker.patch(
        "tools.summary_tools.get_settings", return_value=SimpleNamespace(watched_dirs=[Path("~/Downloads")])
    )
    mocker.patch(
        "tools.summary_tools.list_recent",
        return_value=[_file("C:/Downloads/invoice.pdf"), _file("C:/Downloads/report.docx")],
    )
    mocker.patch(
        "tools.summary_tools.extract_document_text",
        side_effect=lambda path: "Invoice content." if path.name == "invoice.pdf" else "Report content.",
    )
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "digest of today's downloads"

    result = summarize_todays_downloads(provider)

    assert result == "digest of today's downloads"
    provider.complete.assert_called_once()
    prompt = provider.complete.call_args[0][0]
    assert "Invoice content." in prompt
    assert "Report content." in prompt


def test_summarize_todays_downloads_uses_real_extracted_text_from_matching_files(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "notes.txt").write_text("Nimbus really did download this file today.")
    mocker.patch("tools.summary_tools.get_settings", return_value=SimpleNamespace(watched_dirs=[downloads]))
    provider = mocker.Mock(spec=LLMProvider)
    provider.complete.return_value = "digest"

    result = summarize_todays_downloads(provider)

    assert result == "digest"
    prompt = provider.complete.call_args[0][0]
    assert "Nimbus really did download this file today." in prompt
