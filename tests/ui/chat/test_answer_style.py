from __future__ import annotations

import pytest

from ui.chat.answer_style import clean_answer

EM = chr(0x2014)
EN = chr(0x2013)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"Paris {EM} the capital {EM} is big", "Paris, the capital, is big"),
        (f"Pages 4{EN}5 cover it", "Pages 4 to 5 cover it"),
        (f"{EM} a dashed bullet", "a dashed bullet"),
        ("no dashes here", "no dashes here"),
        ("built-in hyphens stay", "built-in hyphens stay"),
    ],
)
def test_clean_answer_rewrites_prose(text: str, expected: str) -> None:
    assert clean_answer(text) == expected


def test_clean_answer_leaves_code_blocks_alone() -> None:
    text = "Run this " + EM + " now\n```\nx = a " + EM + " b\n```"

    assert clean_answer(text) == "Run this, now\n```\nx = a " + EM + " b\n```"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Done.\n<tool_code>file:///C:/a.docx</tool_code>", "Done."),
        ("Done.\n<tool_code>file:///C:/a.docx</tool_code", "Done."),
        ("<think>let me plan this</think>The answer is 4.", "The answer is 4."),
        ("Here it is.<|im_end|>", "Here it is."),
        ("Stray </tool_call> closing tag", "Stray  closing tag"),
    ],
)
def test_clean_answer_removes_stray_model_markup(text: str, expected: str) -> None:
    assert clean_answer(text) == expected


def test_clean_answer_keeps_markup_inside_code_blocks() -> None:
    text = "Example:\n```\n<think>x</think>\n```"

    assert clean_answer(text) == text
