from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from core.file_catalog import FileCatalog
from core.retriever import Retriever
from llm.provider import LLMProvider
from models.schema import CatalogMatch, SearchResult
from tools.file_toolbox import MAX_READ_WORDS, MAX_RESULTS, FileToolbox
from tools.registry import ToolRegistry


def _match(path: Path, score: float = 95.0, modified_at: datetime = datetime(2026, 11, 10, 8, 0)) -> CatalogMatch:
    return CatalogMatch(file_path=str(path), file_name=path.name, size_bytes=2048, modified_at=modified_at, score=score)


def _chunk(path: Path, score: float, text: str) -> SearchResult:
    return SearchResult(
        chunk_id=f"{path}:{score}", chunk_text=text, file_path=str(path), file_name=path.name, score=score, metadata={}
    )


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "plan.txt").write_text("alpha beta gamma delta", encoding="utf-8")
    return folder.resolve()


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    folder = tmp_path / "private"
    folder.mkdir()
    path = folder / "secret.txt"
    path.write_text("do not read", encoding="utf-8")
    return path


@pytest.fixture
def catalog(mocker: MockerFixture) -> Mock:
    catalog = mocker.Mock(spec=FileCatalog)
    catalog.search_names.return_value = []
    catalog.recent_files.return_value = []
    return catalog


@pytest.fixture
def retriever(mocker: MockerFixture) -> Mock:
    retriever = mocker.Mock(spec=Retriever)
    retriever.retrieve.return_value = []
    return retriever


@pytest.fixture
def provider(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=LLMProvider)


@pytest.fixture
def toolbox(retriever: Mock, catalog: Mock, shared: Path, provider: Mock) -> FileToolbox:
    return FileToolbox(retriever, catalog, lambda path: shared in path.parents, provider)


def test_register_adds_six_read_only_tools(toolbox: FileToolbox) -> None:
    registry = ToolRegistry()

    toolbox.register(registry)

    assert len(registry.names()) == 6
    assert not any(registry.get(name).requires_confirmation for name in registry.names())


def test_read_file_returns_the_text_and_a_source(toolbox: FileToolbox, shared: Path) -> None:
    result = toolbox.read_file({"path": str(shared / "plan.txt")})

    assert result.content == "plan.txt:\nalpha beta gamma delta"
    assert result.sources[0].file_path == str(shared / "plan.txt")


def test_read_file_flags_a_truncated_read(toolbox: FileToolbox, shared: Path) -> None:
    result = toolbox.read_file({"path": str(shared / "plan.txt"), "max_words": 2})

    assert result.content.startswith("plan.txt:\nalpha beta\n\n[truncated")


def test_read_file_clamps_max_words_to_the_ceiling(toolbox: FileToolbox, shared: Path, mocker: MockerFixture) -> None:
    excerpt = mocker.patch("tools.file_toolbox.read_document_excerpt", return_value=("text", False))

    toolbox.read_file({"path": str(shared / "plan.txt"), "max_words": 999_999})

    assert excerpt.call_args.args[1] == MAX_READ_WORDS


def test_read_file_reads_at_least_one_word(toolbox: FileToolbox, shared: Path, mocker: MockerFixture) -> None:
    excerpt = mocker.patch("tools.file_toolbox.read_document_excerpt", return_value=("text", True))

    toolbox.read_file({"path": str(shared / "plan.txt"), "max_words": -5})

    assert excerpt.call_args.args[1] == 1


def test_read_file_refuses_a_path_outside_the_shared_folders(toolbox: FileToolbox, secret: Path) -> None:
    with pytest.raises(ToolError, match="outside the folders"):
        toolbox.read_file({"path": str(secret)})


def test_read_file_refuses_parent_traversal_out_of_a_shared_folder(
    toolbox: FileToolbox, shared: Path, secret: Path
) -> None:
    sneaky = shared / ".." / secret.parent.name / secret.name

    with pytest.raises(ToolError, match="outside the folders"):
        toolbox.read_file({"path": str(sneaky)})


def test_read_file_resolves_a_bare_file_name_through_the_catalog(
    toolbox: FileToolbox, catalog: Mock, shared: Path
) -> None:
    catalog.search_names.return_value = [_match(shared / "plan.txt")]

    result = toolbox.read_file({"path": "plan.txt"})

    catalog.search_names.assert_called_once_with("plan.txt", limit=1)
    assert "alpha beta" in result.content


def test_read_file_raises_for_a_bare_name_the_catalog_does_not_know(toolbox: FileToolbox) -> None:
    with pytest.raises(ToolError, match="find_files_by_name"):
        toolbox.read_file({"path": "ghost.txt"})


def test_read_file_raises_for_a_missing_file_in_a_shared_folder(toolbox: FileToolbox, shared: Path) -> None:
    with pytest.raises(ToolError, match="doesn't exist"):
        toolbox.read_file({"path": str(shared / "gone.txt")})


def test_search_files_lists_files_with_their_best_excerpt(toolbox: FileToolbox, retriever: Mock, shared: Path) -> None:
    retriever.retrieve.return_value = [
        _chunk(shared / "a.txt", 0.9, "first   excerpt"),
        _chunk(shared / "a.txt", 0.4, "second excerpt"),
        _chunk(shared / "b.txt", 0.7, "other file"),
    ]

    result = toolbox.search_files({"query": "budget"})

    assert result.content.splitlines()[1].strip() == "first excerpt"
    assert [s.file_name for s in result.sources] == ["a.txt", "b.txt"]


def test_search_files_says_so_when_nothing_matches(toolbox: FileToolbox) -> None:
    result = toolbox.search_files({"query": "budget"})

    assert result.content.startswith("No indexed file matched")
    assert result.sources == []


@pytest.mark.parametrize(("limit", "expected"), [(500, MAX_RESULTS), (0, 1)])
def test_search_files_clamps_the_limit(toolbox: FileToolbox, retriever: Mock, limit: int, expected: int) -> None:
    toolbox.search_files({"query": "budget", "limit": limit})

    assert retriever.retrieve.call_args.kwargs["top_k"] == expected * 4


def test_find_files_by_name_lists_matches_with_sources(toolbox: FileToolbox, catalog: Mock, shared: Path) -> None:
    catalog.search_names.return_value = [_match(shared / "plan.txt")]

    result = toolbox.find_files_by_name({"name": "plan"})

    assert result.content.startswith("1. plan.txt: ")
    assert "2.0 KB" in result.content
    assert result.sources[0].file_name == "plan.txt"


def test_find_files_by_name_says_so_when_nothing_matches(toolbox: FileToolbox) -> None:
    assert toolbox.find_files_by_name({"name": "plan"}).content == "No file name looks like 'plan'."


def test_find_files_by_name_clamps_the_limit(toolbox: FileToolbox, catalog: Mock) -> None:
    toolbox.find_files_by_name({"name": "plan", "limit": 1000})

    catalog.search_names.assert_called_once_with("plan", limit=MAX_RESULTS)


def test_list_recent_files_filters_by_folder(toolbox: FileToolbox, catalog: Mock, tmp_path: Path) -> None:
    catalog.recent_files.return_value = [
        _match(tmp_path / "Downloads" / "a.zip"),
        _match(tmp_path / "Documents" / "b.docx"),
    ]

    result = toolbox.list_recent_files({"folder": "downloads"})

    assert [s.file_name for s in result.sources] == ["a.zip"]


def test_list_recent_files_matches_whole_folder_names_only(toolbox: FileToolbox, catalog: Mock, tmp_path: Path) -> None:
    catalog.recent_files.return_value = [
        _match(tmp_path / "Documents" / "a.docx"),
        _match(tmp_path / "doc" / "b.txt"),
    ]

    result = toolbox.list_recent_files({"folder": "doc"})

    assert [s.file_name for s in result.sources] == ["b.txt"]


def test_list_recent_files_starts_today_at_midnight_for_one_day(toolbox: FileToolbox, catalog: Mock) -> None:
    toolbox.list_recent_files({"days": 1})

    since = catalog.recent_files.call_args.args[0]
    assert since == datetime.combine(datetime.now().date(), datetime.min.time())


def test_list_recent_files_says_so_when_nothing_changed(toolbox: FileToolbox) -> None:
    assert toolbox.list_recent_files({}).content == "No files changed in that period."


def test_summarize_file_summarizes_a_shared_file(
    toolbox: FileToolbox, shared: Path, provider: Mock, mocker: MockerFixture
) -> None:
    summarize = mocker.patch("tools.file_toolbox.summarize_document", return_value="- a plan")

    result = toolbox.summarize_file({"path": str(shared / "plan.txt")})

    summarize.assert_called_once_with(shared / "plan.txt", provider)
    assert result.content == "- a plan"


def test_summarize_file_refuses_a_path_outside_the_shared_folders(
    toolbox: FileToolbox, secret: Path, mocker: MockerFixture
) -> None:
    summarize = mocker.patch("tools.file_toolbox.summarize_document")

    with pytest.raises(ToolError):
        toolbox.summarize_file({"path": str(secret)})

    summarize.assert_not_called()


def test_get_file_info_reports_size_and_folder(toolbox: FileToolbox, shared: Path) -> None:
    result = toolbox.get_file_info({"path": str(shared / "plan.txt")})

    assert result.content.startswith("plan.txt\n")
    assert f"Folder: {shared}" in result.content
    assert "Size: 22 B" in result.content


def test_get_file_info_refuses_a_path_outside_the_shared_folders(toolbox: FileToolbox, secret: Path) -> None:
    with pytest.raises(ToolError):
        toolbox.get_file_info({"path": str(secret)})
