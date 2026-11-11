from __future__ import annotations

import sys
from pathlib import Path

import pytest

import core.code_runner as runner_module
from config.settings import MIN_CODE_MEMORY_MB
from config.settings_store import save_user_settings
from core.code_runner import _made_files, run_python

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


def test_made_files_includes_a_subfolder_and_skips_bookkeeping(tmp_path: Path) -> None:
    folder = tmp_path / "run"
    (folder / ".temp").mkdir(parents=True)
    (folder / ".temp" / "cache").write_text("x", encoding="utf-8")
    (folder / "script.py").write_text("print(1)", encoding="utf-8")
    (folder / "job.json").write_text("{}", encoding="utf-8")
    (folder / "out").mkdir()
    (folder / "out" / "table.csv").write_text("a", encoding="utf-8")
    (folder / "chart.png").write_bytes(b"png")

    assert [path.name for path in _made_files(folder)] == ["chart.png", "table.csv"]


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


@windows_only
def test_run_python_stops_at_the_memory_limit_from_settings(shared: Path) -> None:
    save_user_settings({"code_memory_limit_mb": 400})

    result = run_python("big = bytearray(900 * 1024 * 1024)\nprint('allocated')", [shared])

    assert result.exit_code != 0
    assert "MemoryError" in result.output and "allocated" not in result.output


@windows_only
def test_run_python_works_at_the_smallest_memory_limit(shared: Path) -> None:
    save_user_settings({"code_memory_limit_mb": MIN_CODE_MEMORY_MB})

    result = run_python("import pandas as pd\nprint(pd.Series([1, 2, 3]).sum())", [shared])

    assert result.exit_code == 0 and result.output.strip() == "6"


@windows_only
@pytest.mark.parametrize(
    ("code", "event"),
    [
        (
            "import _winapi\n"
            "_winapi.CreateProcess(None, 'nimbus_missing_program.exe', None, None, False, 0, None, None, None)",
            "_winapi.CreateProcess",
        ),
        ("import os\nos.startfile('nimbus_missing_file.txt')", "os.startfile"),
        ("import _winapi\n_winapi.CreateJunction('C:/Windows', 'escape')", "_winapi.CreateJunction"),
        ("import _winapi\n_winapi.CreateFile('nimbus_missing.txt', 0x40000000, 0, 0, 2, 0, 0)", "_winapi.CreateFile"),
        ("import _winapi, os\n_winapi.OpenProcess(0x0001, False, os.getppid())", "_winapi.OpenProcess"),
        (
            "import importlib, ctypes\nimportlib.reload(ctypes)\n"
            "ctypes.windll.kernel32.WinExec(b'nimbus_missing_program', 0)",
            "ctypes.",
        ),
    ],
)
def test_run_python_refuses_known_escape_routes(shared: Path, code: str, event: str) -> None:
    # The targets don't exist, so even a broken guard couldn't start anything; the check is
    # that the guard itself refused, by name.
    result = run_python(code, [shared])

    assert "Not allowed in Nimbus's code runner" in result.output and event in result.output


@windows_only
def test_run_python_opens_sqlite_only_in_its_own_folder(shared: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.db"
    code = "\n".join(
        [
            "import sqlite3",
            "con = sqlite3.connect('mine.db')",
            "con.execute('create table t (x)')",
            "con.close()",
            "print('own folder ok')",
            f"sqlite3.connect({str(outside)!r})",
        ]
    )

    result = run_python(code, [shared])

    assert "own folder ok" in result.output and "Can only open SQLite databases" in result.output
    assert not outside.exists()


@windows_only
def test_run_python_copies_a_shared_file_in_but_not_out(shared: Path, tmp_path: Path) -> None:
    leak = tmp_path / "leak.csv"
    code = "\n".join(
        [
            "import shutil",
            f"shutil.copy2({str(shared / 'numbers.csv')!r}, 'copy.csv')",
            "print('copied in')",
            f"shutil.copy2('copy.csv', {str(leak)!r})",
        ]
    )

    result = run_python(code, [shared])

    assert "copied in" in result.output and "Can only" in result.output
    assert not leak.exists()
