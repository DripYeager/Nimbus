from __future__ import annotations

from llm.prompts import build_intent_classify_prompt, build_qa_prompt, build_summarize_prompt
from models.schema import Intent, SearchResult


def test_build_summarize_prompt_includes_the_document_text() -> None:
    prompt = build_summarize_prompt("The quarterly report shows revenue up 12%.")
    assert "The quarterly report shows revenue up 12%." in prompt


def test_build_qa_prompt_includes_context_and_question() -> None:
    chunks = [
        SearchResult(chunk_text="Termination requires 30 days notice.", file_path="c:/contract.pdf",
                     file_name="contract.pdf", score=0.9, metadata={}),
    ]
    prompt = build_qa_prompt("What does the contract say about termination?", chunks)
    assert "Termination requires 30 days notice." in prompt
    assert "[contract.pdf]" in prompt
    assert "What does the contract say about termination?" in prompt


def test_build_qa_prompt_with_no_chunks_has_empty_context() -> None:
    prompt = build_qa_prompt("anything?", [])
    assert "Context:\n\n\nQuestion:" in prompt


def test_build_intent_classify_prompt_lists_every_intent() -> None:
    prompt = build_intent_classify_prompt("find my resume")
    for intent in Intent:
        assert intent.value in prompt


def test_build_intent_classify_prompt_includes_the_request_text() -> None:
    prompt = build_intent_classify_prompt("find my resume")
    assert "find my resume" in prompt
