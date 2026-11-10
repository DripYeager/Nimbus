from __future__ import annotations

import pytest

from ui.chat.answer_style import remove_dashes

EM = "—"
EN = "–"


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
def test_remove_dashes_rewrites_prose(text: str, expected: str) -> None:
    assert remove_dashes(text) == expected


def test_remove_dashes_leaves_code_blocks_alone() -> None:
    text = f"Run this {EM} now\n```\nx = a {EM} b\n```"

    assert remove_dashes(text) == f"Run this, now\n```\nx = a {EM} b\n```"
