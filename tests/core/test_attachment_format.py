from __future__ import annotations

from core.attachment_format import split_attachments, with_attachment


def test_with_attachment_appends_a_named_block() -> None:
    message = with_attachment("Summarize it", "report.pdf", "Q3 revenue grew")

    assert message == 'Summarize it\n\n<attachment name="report.pdf">\nQ3 revenue grew\n</attachment>'


def test_with_attachment_keeps_quotes_out_of_the_name() -> None:
    assert "name=\"my 'best' doc\"" in with_attachment("hi", 'my "best" doc', "x")


def test_split_attachments_returns_the_typed_text_and_names() -> None:
    message = with_attachment("What does this say?", "Screenshot", "line one\nline two")

    assert split_attachments(message) == ("What does this say?", ["Screenshot"])


def test_split_attachments_leaves_plain_messages_alone() -> None:
    assert split_attachments("just a question") == ("just a question", [])
