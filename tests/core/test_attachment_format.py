from __future__ import annotations

from core.attachment_format import AttachedItem, has_attachment, split_attachments, with_attachment


def test_with_attachment_appends_a_named_block() -> None:
    message = with_attachment("Summarize it", "report.pdf", "Q3 revenue grew")

    assert message == 'Summarize it\n\n<attachment name="report.pdf">\nQ3 revenue grew\n</attachment>'


def test_with_attachment_keeps_quotes_out_of_the_name() -> None:
    assert "name=\"my 'best' doc\"" in with_attachment("hi", 'my "best" doc', "x")


def test_split_attachments_returns_the_typed_text_and_names() -> None:
    message = with_attachment("What does this say?", "Screenshot", "line one\nline two")

    assert split_attachments(message) == ("What does this say?", [AttachedItem("Screenshot")])


def test_split_attachments_leaves_plain_messages_alone() -> None:
    assert split_attachments("just a question") == ("just a question", [])


def test_with_attachment_records_the_file_so_it_can_be_previewed_later() -> None:
    message = with_attachment("What does this say?", "Screenshot", "text", path="C:/shots/a.png")

    assert split_attachments(message)[1] == [AttachedItem("Screenshot", "C:/shots/a.png")]


def test_has_attachment_spots_a_block() -> None:
    assert (has_attachment(with_attachment("q", "n", "b")), has_attachment("plain")) == (True, False)
