"""
Reads Nimbus's own command-line options. There's one: --ask <path>, which File Explorer's
right-click entry passes so Nimbus opens with that file attached. Parsing only.
"""

from __future__ import annotations

from collections.abc import Sequence

ASK_FLAG = "--ask"


def ask_path_from(argv: Sequence[str]) -> str | None:
    """The file after --ask, or None when there isn't one."""
    args = list(argv[1:])
    if ASK_FLAG not in args:
        return None
    index = args.index(ASK_FLAG)
    if index + 1 >= len(args) or not args[index + 1].strip():
        return None
    return args[index + 1]
