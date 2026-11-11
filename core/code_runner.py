"""
Runs user-approved Python in a separate, locked-down process: a fresh scratch folder per run
(the only place it may write, under Documents\\Nimbus\\Code runs), the user's shared folders to
read, Python's isolated mode, a hidden window, no input, a Windows job object that caps memory
and kills the run with Nimbus, and a time limit. Returns what the code printed and the files it
made. Owns the parent side; the rules applied inside the run live in core/code_sandbox.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psutil

from config.paths import is_frozen
from config.settings import get_settings
from core.code_sandbox import RUN_CODE_FLAG
from core.command_runner import trim_output
from core.exceptions import ToolError
from core.logger import get_logger

logger = get_logger(__name__)

RUNS_DIR = Path("~/Documents/Nimbus/Code runs")
DEFAULT_TIMEOUT_S = 60.0
BYTES_PER_MB = 1024**2
# Plenty for spreadsheet-sized work; see _environment.
MATH_THREADS = "4"
SANDBOX_SCRIPT = Path(__file__).with_name("code_sandbox.py")
INTERNAL_FILES = frozenset({"script.py", "job.json"})


@dataclass(frozen=True)
class CodeResult:
    exit_code: int
    output: str
    folder: Path
    files: list[Path] = field(default_factory=list)
    timed_out: bool = False


def run_python(code: str, read_roots: list[Path], timeout_s: float = DEFAULT_TIMEOUT_S) -> CodeResult:
    """Runs code in its own process and folder; returns its output and new files.

    Raises:
        ToolError: The run couldn't be started.
    """
    folder = _new_run_folder()
    process = _start(_write_job(folder, code, read_roots), folder)
    job_handle = _limit(process, get_settings().code_memory_limit_mb * BYTES_PER_MB)
    try:
        raw, _ = process.communicate(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        raw, _ = process.communicate()
        timed_out = True
    finally:
        _close(job_handle)
    output = trim_output(raw.decode("utf-8", errors="replace").replace("\r\n", "\n"))
    return CodeResult(process.returncode if not timed_out else -1, output, folder, _made_files(folder), timed_out)


def _write_job(folder: Path, code: str, read_roots: list[Path]) -> Path:
    """Saves the code (script.py, for the user to see) and the sandbox's instructions."""
    (folder / "script.py").write_text(code, encoding="utf-8")
    job = folder / "job.json"
    job.write_text(
        json.dumps({"code": code, "scratch": str(folder), "read_roots": [str(root) for root in read_roots]}),
        encoding="utf-8",
    )
    return job


def _start(job: Path, folder: Path) -> subprocess.Popen[bytes]:
    """Starts the sandbox hidden, in the run folder, with output captured."""
    try:
        return subprocess.Popen(
            _command(job),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(folder),
            env=_environment(folder),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        raise ToolError(f"Couldn't start Python: {e}") from e


def _command(job: Path) -> list[str]:
    """The packaged app runs code through itself; from source it's isolated-mode Python."""
    if is_frozen():
        return [sys.executable, RUN_CODE_FLAG, str(job)]
    return [sys.executable, "-I", "-X", "utf8", str(SANDBOX_SCRIPT), str(job)]


def _environment(folder: Path) -> dict[str, str]:
    """Charts render off-screen, temp and cache files land in the run's own folder, and numpy's
    math library uses a few threads: by default it reserves memory for every CPU thread, which
    on a many-core PC is more than a modest memory limit allows before any code runs."""
    temp = folder / ".temp"
    temp.mkdir(exist_ok=True)
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    environment.update(
        {
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(temp),
            "TEMP": str(temp),
            "TMP": str(temp),
            "PYTHONIOENCODING": "utf-8",
            "OPENBLAS_NUM_THREADS": MATH_THREADS,
            "OMP_NUM_THREADS": MATH_THREADS,
        }
    )
    return environment


def _new_run_folder() -> Path:
    base = RUNS_DIR.expanduser()
    folder = base / datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
    try:
        folder.mkdir(parents=True)
    except OSError as e:
        raise ToolError(f"Couldn't create a folder for the run in {base}: {e}") from e
    return folder


def _made_files(folder: Path) -> list[Path]:
    """What the code created, including in subfolders, without the run's bookkeeping or temp files."""
    files = []
    for path in folder.rglob("*"):
        if not path.is_file() or ".temp" in path.parts:
            continue
        if path.parent == folder and path.name in INTERNAL_FILES:
            continue
        files.append(path)
    return sorted(files)


def _limit(process: subprocess.Popen[bytes], memory_bytes: int) -> object | None:
    """A job object with a memory cap (from Settings) that also ends the run if Nimbus itself
    goes away."""
    try:
        import win32api
        import win32con
        import win32job

        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        info["ProcessMemoryLimit"] = memory_bytes
        info["BasicLimitInformation"]["LimitFlags"] = (
            win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY | win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, process.pid)
        try:
            win32job.AssignProcessToJobObject(job, handle)
        finally:
            win32api.CloseHandle(handle)
        return job
    except Exception as e:
        # The time limit still applies; a missing memory cap isn't worth failing the run over.
        logger.warning("Couldn't put the code run in a job object", extra={"error": str(e)})
        return None


def _close(job: object | None) -> None:
    if job is not None:
        try:
            import win32api

            win32api.CloseHandle(job)
        except Exception:
            pass


def _kill_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass
