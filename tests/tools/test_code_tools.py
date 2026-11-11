from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.code_runner import CodeResult
from core.exceptions import ToolError
from tools.code_tools import CodeToolbox, describe_code, describe_failure, describe_run
from tools.registry import ToolRegistry

SHARED = Path("C:/Users/alex/Documents")


@pytest.fixture
def runner(mocker: MockerFixture, tmp_path: Path) -> Mock:
    chart = tmp_path / "chart_1.png"
    chart.write_bytes(b"png")
    return mocker.patch(
        "tools.code_tools.run_python",
        return_value=CodeResult(exit_code=0, output="total 360", folder=tmp_path, files=[chart]),
    )


def test_run_python_passes_the_shared_folders_and_returns_files(runner: Mock) -> None:
    result = CodeToolbox(lambda: [SHARED]).run_python({"code": "print('x')"})

    assert runner.call_args.args == ("print('x')", [SHARED])
    assert "total 360" in result.content and [s.file_name for s in result.sources] == ["chart_1.png"]


def test_run_python_refuses_empty_code(runner: Mock) -> None:
    with pytest.raises(ToolError):
        CodeToolbox(lambda: [SHARED]).run_python({"code": " "})


def test_describe_code_shows_the_whole_program() -> None:
    code = "import pandas as pd\nprint(1)"

    assert describe_code({"code": code}).endswith(code)


def test_describe_run_explains_a_failure(tmp_path: Path) -> None:
    text = describe_run(CodeResult(exit_code=1, output="ZeroDivisionError", folder=tmp_path))

    assert "failed" in text and "ZeroDivisionError" in text


def test_describe_run_leads_with_the_actual_error(tmp_path: Path) -> None:
    traceback = "Traceback (most recent call last):\n" + "  deep pandas line\n" * 40 + "KeyError: 'Total Spend'"

    text = describe_run(CodeResult(exit_code=1, output=traceback, folder=tmp_path))

    assert text.startswith("The code failed with KeyError: 'Total Spend'")
    assert text.count("deep pandas line") < 12


def test_register_always_asks_and_never_offers_always_allow() -> None:
    registry = ToolRegistry()

    CodeToolbox(lambda: [SHARED]).register(registry)

    tool = registry.get("run_python")
    assert tool is not None and tool.needs_confirmation({"code": "print(1)"}) and not tool.always_allowable


def test_describe_failure_finds_the_error_when_output_follows_it() -> None:
    output = "Traceback (most recent call last):\n  File \"script.py\", line 2\nKeyError: 'Sales'\nprinted late"

    assert describe_failure(output).startswith("The code failed with KeyError: 'Sales'")
