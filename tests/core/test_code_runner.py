from __future__ import annotations

import sys
from pathlib import Path

import pytest

import core.code_runner as runner_module
from core.code_runner import run_python

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="The sandbox targets Windows")


@pytest.fixture(autouse=True)
def runs_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Runs go to a temporary folder, never to the real Documents."""
    folder = tmp_path / "runs"
    monkeypatch.setattr(runner_module, "RUNS_DIR", folder)
    return folder


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "numbers.csv").write_text("value\n2\n3\n5\n", encoding="utf-8")
    return folder


@windows_only
def test_run_python_prints_results(shared: Path) -> None:
    result = run_python("print(6 * 7)", [shared])

    assert (result.exit_code, result.output) == (0, "42")


@windows_only
def test_run_python_reads_a_shared_file_with_pandas(shared: Path) -> None:
    code = f"import pandas as pd\nprint(pd.read_csv(r'{shared / 'numbers.csv'}')['value'].sum())"

    assert run_python(code, [shared]).output == "10"


@windows_only
def test_run_python_saves_an_unsaved_chart(shared: Path) -> None:
    result = run_python("import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])", [shared])

    assert [path.name for path in result.files] == ["chart_1.png"]


@windows_only
def test_run_python_cannot_write_into_a_shared_folder(shared: Path) -> None:
    result = run_python(f"open(r'{shared / 'new.txt'}', 'w').write('x')", [shared])

    assert result.exit_code != 0 and "Can only write" in result.output
    assert not (shared / "new.txt").exists()


@windows_only
@pytest.mark.parametrize(
    "code",
    [
        "import subprocess; subprocess.run(['cmd', '/c', 'echo hi'])",
        "import os; os.system('echo hi')",
        "import socket; socket.create_connection(('example.com', 80))",
        "import ctypes; ctypes.windll.kernel32.WinExec(b'calc', 1)",
    ],
)
def test_run_python_blocks_programs_network_and_native_calls(shared: Path, code: str) -> None:
    result = run_python(code, [shared])

    assert result.exit_code != 0 and not result.timed_out


@windows_only
def test_run_python_stops_code_that_runs_too_long(shared: Path) -> None:
    result = run_python("while True:\n    pass", [shared], timeout_s=3)

    assert result.timed_out is True
