from __future__ import annotations

from datetime import datetime

from llm.prompts import build_qa_prompt, build_summarize_prompt, build_system_prompt
from models.schema import SearchResult


def test_build_system_prompt_lists_the_shared_folders() -> None:
    prompt = build_system_prompt(["Downloads", "Documents"], datetime(2026, 11, 10, 9, 5))

    assert "Folders you can see: Downloads, Documents" in prompt


def test_build_system_prompt_says_when_no_folders_are_shared() -> None:
    prompt = build_system_prompt([], datetime(2026, 11, 10, 9, 5))

    assert "Folders you can see: none yet" in prompt


def test_build_system_prompt_has_the_date_but_not_the_minute() -> None:
    """The same all day, so a local model can reuse its cached work between turns."""
    morning = build_system_prompt([], datetime(2026, 11, 10, 9, 5))

    assert "Tuesday 10 November 2026" in morning and "09:05" not in morning
    assert morning == build_system_prompt([], datetime(2026, 11, 10, 17, 42))


def test_build_system_prompt_names_the_search_tools() -> None:
    prompt = build_system_prompt([], datetime(2026, 11, 10))

    assert "search_files" in prompt
    assert "find_files_by_name" in prompt


def test_build_summarize_prompt_includes_the_document_text() -> None:
    prompt = build_summarize_prompt("The quarterly report shows revenue up 12%.")

    assert "The quarterly report shows revenue up 12%." in prompt


def test_build_qa_prompt_includes_context_and_question() -> None:
    chunks = [
        SearchResult(
            chunk_id="1",
            chunk_text="Termination requires 30 days notice.",
            file_path="c:/contract.pdf",
            file_name="contract.pdf",
            score=0.9,
            metadata={},
        ),
    ]

    prompt = build_qa_prompt("What does the contract say about termination?", chunks)

    assert "[contract.pdf] Termination requires 30 days notice." in prompt
    assert "Question: What does the contract say about termination?" in prompt


def test_build_qa_prompt_with_no_chunks_has_empty_context() -> None:
    prompt = build_qa_prompt("anything?", [])

    assert "Context:\n\n\nQuestion:" in prompt
