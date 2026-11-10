from __future__ import annotations

import pytest

from core.launch_args import ask_path_from


def test_ask_path_from_reads_the_file_after_the_flag() -> None:
    assert ask_path_from(["Nimbus.exe", "--ask", "C:/Docs/Q3 report.pdf"]) == "C:/Docs/Q3 report.pdf"


@pytest.mark.parametrize("argv", [["Nimbus.exe"], ["Nimbus.exe", "--ask"], ["Nimbus.exe", "--ask", "  "]])
def test_ask_path_from_is_none_without_a_file(argv: list[str]) -> None:
    assert ask_path_from(argv) is None
