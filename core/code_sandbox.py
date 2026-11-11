"""
The inside of a code run: this module is the separate process's entry point. It installs a
Python audit hook before the user-approved code starts, then runs it. The hook lets the code
read the user's shared folders, the run's scratch folder and Python's own files, write only
to the scratch folder, and never start programs, open network connections or change the
registry. Afterwards any chart left open is saved as a PNG. Standard library only, so it runs
the same from source and from the packaged app. Audit hooks are a guardrail, not a hard
security boundary: the approval card showing the exact code is the first line of defence.

    python -I code_sandbox.py job.json        (Nimbus.exe --run-code job.json when packaged)
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from pathlib import Path

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
# Events that change files: every path they name must be inside the scratch folder.
FILE_CHANGES = frozenset(
    {
        "os.remove",
        "os.rename",
        "os.replace",
        "os.rmdir",
        "os.mkdir",
        "os.chmod",
        "os.truncate",
        "os.link",
        "os.symlink",
        "shutil.rmtree",
        "shutil.move",
        "shutil.copyfile",
        "os.utime",
    }
)
# ctypes reaches any Windows function directly, so loading or looking up native code is blocked.
# numpy, pandas and matplotlib use it while importing, so they're imported before the guard.
BLOCKED_PREFIXES = (
    "subprocess.",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.startfile",
    "os.kill",
    "socket.connect",
    "socket.bind",
    "socket.getaddrinfo",
    "socket.sendto",
    "winreg.Create",
    "winreg.Set",
    "winreg.Delete",
    "ctypes.dlopen",
    "ctypes.dlsym",
    "ctypes.call_function",
    "_winapi.CreateProcess",
    # A junction made in the run's folder could point anywhere; other processes are off limits.
    "_winapi.CreateJunction",
    "_winapi.OpenProcess",
    "_winapi.TerminateProcess",
    # Raw Windows file and pipe handles would go around the checks on open().
    "_winapi.CreateFile",
    "_winapi.CreateNamedPipe",
    "webbrowser.open",
)
# Listing a folder reveals its file names, so it counts as reading.
DIRECTORY_LISTINGS = frozenset({"os.listdir", "os.scandir"})
CHART_NAME = "chart_{index}.png"
# How the packaged app is asked to act as this sandbox instead of starting Nimbus.
RUN_CODE_FLAG = "--run-code"
PRELOADED = ("numpy", "pandas", "openpyxl", "matplotlib.pyplot")


class Policy:
    """Which paths the code may read and write."""

    def __init__(self, scratch: Path, read_roots: list[Path]) -> None:
        self.scratch = scratch.resolve()
        python_dirs = {Path(p).resolve() for p in (sys.prefix, sys.base_prefix, sys.exec_prefix)}
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            python_dirs.add(Path(bundle).resolve())
            # The packaged app keeps the standard library in an archive inside the exe itself,
            # so imports read it; just that one file, not the folder around it.
            python_dirs.add(Path(sys.executable).resolve())
        fonts = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "Fonts"
        self.readable = [self.scratch, *python_dirs, fonts.resolve(), *(r.resolve() for r in read_roots)]

    def may_read(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.readable)

    def may_write(self, path: Path) -> bool:
        return path == self.scratch or self.scratch in path.parents


def install_guard(policy: Policy) -> None:
    """Adds the audit hook; once added, Python offers no way to remove it."""

    def guard(event: str, args: tuple[object, ...]) -> None:
        if event.startswith(BLOCKED_PREFIXES):
            raise PermissionError(f"Not allowed in Nimbus's code runner: {event}")
        if event == "open":
            _check_open(policy, args)
        elif event in DIRECTORY_LISTINGS:
            path = _as_path(args[0]) if args else None
            if path is not None and not policy.may_read(path):
                raise PermissionError(f"Can only look inside the folders shared with Nimbus, not {path}")
        elif event in FILE_CHANGES:
            for value in args:
                path = _as_path(value)
                if path is not None and not policy.may_write(path):
                    raise PermissionError(f"Can only change files in the run's folder, not {path}")
        elif event == "_winapi.CopyFile2":
            _check_copy(policy, args)
        elif event == "sqlite3.connect":
            _check_database(policy, args)

    sys.addaudithook(guard)


def _check_copy(policy: Policy, args: tuple[object, ...]) -> None:
    """shutil's fast copy on Windows: read from where reading is allowed, write only here."""
    source, target = (_as_path(value) for value in args[:2])
    if source is None or not policy.may_read(source):
        raise PermissionError(f"Can only copy from the folders shared with Nimbus, not {source}")
    if target is None or not policy.may_write(target):
        raise PermissionError(f"Can only copy into the run's folder, not {target}")


def _check_database(policy: Policy, args: tuple[object, ...]) -> None:
    """SQLite opens files for writing, so only databases in the run's folder (or in memory).
    To look at a shared database, copy it into the run's folder first."""
    database = args[0] if args else None
    if database in ("", ":memory:", b"", b":memory:"):
        return
    path = None if str(database).startswith("file:") else _as_path(database)
    if path is None or not policy.may_write(path):
        raise PermissionError(
            "Can only open SQLite databases in the run's folder; copy a shared one there first with shutil.copy."
        )


def _check_open(policy: Policy, args: tuple[object, ...]) -> None:
    path = _as_path(args[0]) if args else None
    if path is None:
        return
    mode = args[1] if len(args) > 1 and isinstance(args[1], str) else "r"
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    writing = any(char in mode for char in "wax+") or bool(flags & WRITE_FLAGS)
    if writing and not policy.may_write(path):
        raise PermissionError(f"Can only write files in the run's folder ({policy.scratch}), not {path}")
    if not writing and not policy.may_read(path):
        raise PermissionError(f"Can only read files in the folders shared with Nimbus, not {path}")


def _as_path(value: object) -> Path | None:
    """An absolute path for a str/bytes/PathLike argument, with links followed so a junction
    inside a shared folder can't point at the rest of the disk. None for file descriptors."""
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    if not isinstance(value, (str, os.PathLike)):
        return None
    try:
        return Path(value).resolve()
    except (OSError, RuntimeError) as e:
        raise PermissionError("Can't use that path in Nimbus's code runner.") from e


def save_open_charts(scratch: Path) -> None:
    """Saves charts the code drew but didn't save itself, so "make a chart" always yields a file."""
    pyplot = sys.modules.get("matplotlib.pyplot")
    if pyplot is None or any(scratch.glob("*.png")):
        return
    for index, number in enumerate(pyplot.get_fignums(), start=1):
        pyplot.figure(number).savefig(scratch / CHART_NAME.format(index=index), dpi=150, bbox_inches="tight")


def attach_std_streams() -> None:
    """A windowed (packaged) app starts with no stdout or stderr, so print() would vanish.
    Reconnects them to the pipes the parent passed in, before the guard blocks native calls."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    for handle_id, name in ((-11, "stdout"), (-12, "stderr")):
        handle = kernel32.GetStdHandle(handle_id)
        if handle and handle != -1:
            descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY)
            # Lives as long as the process: it *is* the run's stdout or stderr from here on.
            stream = open(descriptor, "w", encoding="utf-8", buffering=1, closefd=False)  # noqa: SIM115
            setattr(sys, name, stream)


def preload_libraries() -> None:
    """Imports the data libraries while native loading is still allowed; any that aren't
    installed are simply left out. matplotlib's notes ("building the font cache") would land in
    the run's output as if the code had printed them, so only its errors are kept."""
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    for name in PRELOADED:
        try:
            importlib.import_module(name)
        except ImportError:
            continue


def run_job(job_file: Path) -> None:
    """Reads the job, locks the process down, then runs the code as __main__ in the scratch folder."""
    job = json.loads(job_file.read_text(encoding="utf-8"))
    scratch = Path(job["scratch"])
    os.chdir(scratch)
    script = scratch / "script.py"
    code = compile(job["code"], str(script), "exec")
    preload_libraries()
    install_guard(Policy(scratch, [Path(root) for root in job["read_roots"]]))
    try:
        exec(code, {"__name__": "__main__", "__file__": str(script)})  # noqa: S102 - approved by the user
    finally:
        # What the code printed goes out before any traceback, so the error ends the output.
        sys.stdout.flush()
    save_open_charts(scratch)


if __name__ == "__main__":
    run_job(Path(sys.argv[1]))
