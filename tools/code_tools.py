"""
The run_python tool: lets the assistant do real calculations and data work on the user's files
("total column C in this Excel", "chart my monthly spending") by running Python it writes. Every
run waits for the user's approval on a card that shows the whole code; there's no "always
allow". The run reads only the shared folders, writes only to its own new folder under
Documents/Nimbus/Code runs, and the files it makes come back as clickable sources. Owns the
tool's wording and result; the containment lives in core/code_runner.py and core/code_sandbox.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.code_runner import DEFAULT_TIMEOUT_S, CodeResult, run_python
from core.exceptions import ToolError
from models.chat import ShownCode, ToolResult
from tools.file_tools import source_ref_for
from tools.registry import Tool, ToolRegistry, object_schema, string_param, tool_spec

RUN_PYTHON = tool_spec(
    "run_python",
    "Run Python code for calculations and data work on the user's files: totals and averages, reading "
    "Excel/CSV with pandas, charts with matplotlib (save with plt.savefig('name.png'); charts left open are "
    "saved too). numpy, pandas, openpyxl and matplotlib are available. Use full paths for input files (find "
    "them with find_files_by_name first). The code may read only the folders the user shared and writes only "
    "to its own run folder, which is the current directory. No internet, no other programs. Print the results. "
    "If you don't know a file's layout, print df.columns and df.head() first, then use the real column names.",
    object_schema({"code": string_param("The complete Python program to run")}, ["code"]),
)
NO_OUTPUT = "(The code printed nothing.)"
FAILURE_TAIL_LINES = 12
OUT_OF_MEMORY_HINT = (
    "It used up the memory allowed for code runs. Tell the user they can raise the limit in "
    "Settings, General, or try reading less of the data at once."
)
# A traceback's last line: "KeyError: 'Sales'", "pandas.errors.ParserError: ...".
ERROR_LINE = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt|Warning)\b")


class CodeToolbox:
    """shared_roots lists the folders the code may read."""

    def __init__(self, shared_roots: Callable[[], list[Path]]) -> None:
        self._shared_roots = shared_roots

    def register(self, registry: ToolRegistry) -> None:
        registry.register(
            Tool(
                RUN_PYTHON,
                self.run_python,
                describe_code,
                requires_confirmation=True,
                always_allowable=False,
                can_skip_in_settings=True,
                show_code=show_code,
            )
        )

    def run_python(self, args: dict[str, Any]) -> ToolResult:
        code = str(args.get("code", "")).strip()
        if not code:
            raise ToolError("No code was given.")
        result = run_python(code, self._shared_roots())
        return ToolResult(content=describe_run(result), sources=[source_ref_for(path) for path in result.files])


def describe_code(args: dict[str, Any]) -> str:
    """The chip and card line; the whole program is shown under it (show_code)."""
    return "Run Python code"


def show_code(args: dict[str, Any]) -> ShownCode:
    return ShownCode(title="Python", text=str(args.get("code", "")).strip())


def describe_failure(output: str) -> str:
    """The error itself first (a traceback's last line names it), then the end of the traceback:
    the lines deep inside pandas or numpy rarely help, the user's own line and the error do."""
    lines = [line for line in output.splitlines() if line.strip()]
    errors = [line for line in lines if ERROR_LINE.match(line)]
    error = errors[-1] if errors else (lines[-1] if lines else "an unknown error")
    tail = "\n".join(lines[-FAILURE_TAIL_LINES:])
    hint = f"\n{OUT_OF_MEMORY_HINT}" if error.startswith("MemoryError") else ""
    return f"The code failed with {error}{hint}\nEnd of the traceback:\n{tail}"


def describe_run(result: CodeResult) -> str:
    """What the model reads back: the output, how it ended, and the files it made."""
    lines = []
    if result.timed_out:
        lines.append(f"(Stopped after {DEFAULT_TIMEOUT_S:.0f} seconds.)")
        lines.append(result.output or NO_OUTPUT)
    elif result.exit_code != 0:
        lines.append(describe_failure(result.output))
    else:
        lines.append(result.output or NO_OUTPUT)
    if result.files:
        lines.append(f"Files made in {result.folder}: " + ", ".join(path.name for path in result.files))
    return "\n".join(lines)
