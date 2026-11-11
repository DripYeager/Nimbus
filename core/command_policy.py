"""
Decides how much trust a terminal command needs. Read-only information commands (ipconfig,
systeminfo, Get-Process, ping...) may run without asking; anything else waits for the user's
approval; asking for administrator rights is refused outright. The read-only test is strict on
purpose: the first command must be on an allow-list (native tools also have their arguments
checked, so "ipconfig /release" isn't free), anything after a pipe may only sort, filter or
format, and characters that could smuggle in more code are not allowed at all. Pure text
analysis; running the command is command_runner's job.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from core.command_text import blank_single_quoted, has_path, is_system_path, program_name, resolves_to_windows

# Chaining, redirection, sub-expressions, script blocks, variables, escapes and line breaks: any
# of these could hide a second command inside an innocent-looking one. (";" is allowed because
# every statement it separates is checked on its own.)
_UNSAFE_CHARACTERS = re.compile(r"[&<>`$(){}@\r\n]|\|\|")
# One word: unquoted characters and quoted runs, so findstr /c:"IPv4 Address" stays one word.
_WORD = re.compile(r"""(?:[^\s"']|"[^"]*"|'[^']*')+""")
_ELEVATION = re.compile(r"-verb\s+runas|\brunas(\.exe)?\b|\bsudo\b|\bgsudo\b", re.IGNORECASE)
ELEVATION_MESSAGE = "Nimbus never runs commands as administrator. Run that one yourself if it's needed."

ArgumentRule = Callable[[list[str]], bool]


def _any(_: list[str]) -> bool:
    return True


def _only(*allowed: str) -> ArgumentRule:
    """Every argument must be one of allowed (case-insensitive); no arguments is fine too."""
    permitted = {value.lower() for value in allowed}
    return lambda args: all(arg.lower() in permitted for arg in args)


def _starts_with(*prefixes: tuple[str, ...]) -> ArgumentRule:
    """The arguments must begin with one of the given word sequences (case-insensitive)."""

    def rule(args: list[str]) -> bool:
        lowered = [arg.lower() for arg in args]
        return any(lowered[: len(prefix)] == list(prefix) for prefix in prefixes)

    return rule


# PowerShell cmdlets that only read. Any arguments are fine: the character check above already
# rules out script blocks and sub-expressions.
_READ_ONLY_CMDLETS = [
    "get-process",
    "get-counter",
    "get-service",
    "get-computerinfo",
    "get-netadapter",
    "get-netadapterstatistics",
    "get-netipaddress",
    "get-netipconfiguration",
    "get-netconnectionprofile",
    "get-netroute",
    "get-nettcpconnection",
    "get-dnsclientserveraddress",
    "get-volume",
    "get-psdrive",
    "get-physicaldisk",
    "get-date",
    "get-timezone",
    "get-culture",
    "get-hotfix",
    "get-printer",
    "get-startapps",
    "get-ciminstance",
    "get-wmiobject",
    "get-mpcomputerstatus",
    "test-connection",
    "test-netconnection",
    "resolve-dnsname",
    "gps",
    "ps",
]
# Native tools, each with the arguments that keep it read-only.
_READ_ONLY_TOOLS: dict[str, ArgumentRule] = {
    "ipconfig": _only("/all", "/displaydns"),
    "systeminfo": _any,
    "hostname": _any,
    "whoami": _any,
    "getmac": _any,
    "tasklist": _any,
    "driverquery": _any,
    "ping": _any,
    "tracert": _any,
    "pathping": _any,
    "nslookup": _any,
    "netstat": _any,
    "route": _only("print"),
    "arp": lambda args: bool(args) and args[0].lower() in {"-a", "/a"},
    "netsh": _starts_with(("wlan", "show"), ("interface", "show"), ("interface", "ipv4", "show")),
    "winget": _starts_with(("list",), ("search",), ("show",), ("--version",)),
    "powercfg": _only("/a", "/availablesleepstates", "/requests", "/lastwake", "/getactivescheme", "/list", "/l"),
}
# Select-String's parameters: name -> whether it takes a value. The file ones are refused, and
# listing them keeps a short form like "-pa" (Path or Pattern) from slipping through.
_SELECT_STRING_FILE_PARAMETERS = frozenset({"path", "literalpath", "include", "exclude"})
_SELECT_STRING_PARAMETERS: dict[str, bool] = {
    "pattern": True,
    "context": True,
    "encoding": True,
    "culture": True,
    "simplematch": False,
    "casesensitive": False,
    "notmatch": False,
    "allmatches": False,
    "quiet": False,
    "list": False,
    "raw": False,
    "noemphasis": False,
    **dict.fromkeys(_SELECT_STRING_FILE_PARAMETERS, True),
}
# What may follow a pipe: commands that only sort, filter, measure or format what they're given.
_PIPE_FORMATTERS = frozenset(
    [
        "sort-object",
        "sort",
        "select-object",
        "select",
        "where-object",
        "where",
        "format-table",
        "ft",
        "format-list",
        "fl",
        "measure-object",
        "measure",
        "group-object",
        "group",
        "out-string",
        "select-string",
        "convertto-json",
        "convertto-csv",
        "findstr",
    ]
)


def is_read_only(command: str) -> bool:
    """True when command only reads information, so it may run without the user's approval."""
    if not command.strip() or _ELEVATION.search(command):
        return False
    # Single-quoted text is literal in PowerShell (no variables, no sub-expressions), so its
    # contents can't hide code: a counter path like '\Process(*)\% Processor Time' is fine.
    # Double-quoted text expands $(...), so it gets no such pass. Quotes are read left to right,
    # so a ' inside double quotes can't hide a $(...) between two of them.
    structure = blank_single_quoted(command)
    if structure is None or _UNSAFE_CHARACTERS.search(structure):
        return False
    statements = [statement for statement in structure.split(";") if statement.strip()]
    return bool(statements) and all(_statement_reads_only(statement) for statement in statements)


def _statement_reads_only(statement: str) -> bool:
    """One pipeline: an allow-listed first command, then only sorting, filtering and formatting."""
    segments = [_WORD.findall(segment) for segment in statement.split("|")]
    if any(not words for words in segments):
        return False
    first, *rest = segments
    if not _first_command_reads_only(first):
        return False
    return all(_formats_the_pipeline(words) for words in rest)


def asks_for_elevation(command: str) -> bool:
    """True when command tries to run something as administrator."""
    return bool(_ELEVATION.search(command))


def _first_command_reads_only(words: list[str]) -> bool:
    """An allow-listed cmdlet, or a native tool that is really Windows' own: a path directly in
    System32, or a bare name PowerShell finds there first."""
    token = words[0]
    if has_path(token) and not is_system_path(token):
        return False
    name, args = program_name(token), [arg.strip("'\"") for arg in words[1:]]
    if name in _READ_ONLY_CMDLETS and not has_path(token):
        return True
    rule = _READ_ONLY_TOOLS.get(name)
    if rule is None or not rule(args):
        return False
    return has_path(token) or resolves_to_windows(name)


def _formats_the_pipeline(words: list[str]) -> bool:
    """A pipe stage that only sorts, filters or formats what it was given. It must be the
    PowerShell command itself: "sort.exe" is Windows' sort, which can write a file. findstr and
    Select-String can also read files, so their arguments are checked."""
    token = words[0].strip("'\"")
    name = program_name(token)
    if name not in _PIPE_FORMATTERS:
        return False
    # Only findstr is a program; every other stage must be the PowerShell command by its bare
    # name. "sort.exe" or a path to "sort" is Windows' sort, which can read and write files.
    if name == "findstr":
        if has_path(token) and not is_system_path(token):
            return False
        if not has_path(token) and not resolves_to_windows(name):
            return False
    elif has_path(token) or token.lower().endswith(".exe"):
        return False
    args = words[1:]
    if name == "findstr":
        return _findstr_reads_only_its_input(args)
    if name == "select-string":
        return _select_string_reads_only_its_input(args)
    return True


def _findstr_reads_only_its_input(args: list[str]) -> bool:
    """findstr [switches] string: no /F:, /G: or /D: (they read files; findstr takes "-" for
    "/" too), and no word after the search string, which findstr would open as a file."""
    has_string_switch = False
    plain_words = 0
    for arg in args:
        lowered = arg.strip("'\"").lower()
        switch = "/" + lowered[1:] if lowered.startswith("-") else lowered
        if switch.startswith(("/f:", "/g:", "/d:")):
            return False
        if switch.startswith("/c:"):
            has_string_switch = True
        elif not switch.startswith("/"):
            plain_words += 1
    return plain_words <= (0 if has_string_switch else 1)


def _select_string_reads_only_its_input(args: list[str]) -> bool:
    """Select-String with a pattern only: no -Path or -LiteralPath (or a short form PowerShell
    would accept for them), and no second positional word, which Select-String reads as a path."""
    has_pattern = False
    positional = 0
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if not arg.startswith("-"):
            positional += 1
            continue
        parameter, _, inline_value = arg[1:].lower().partition(":")
        matches = [name for name in _SELECT_STRING_PARAMETERS if name.startswith(parameter)] if parameter else []
        if len(matches) != 1 and parameter not in _SELECT_STRING_PARAMETERS:
            return False
        resolved = parameter if parameter in _SELECT_STRING_PARAMETERS else matches[0]
        if resolved in _SELECT_STRING_FILE_PARAMETERS:
            return False
        has_pattern = has_pattern or resolved == "pattern"
        skip_next = _SELECT_STRING_PARAMETERS[resolved] and not inline_value
    return positional <= (0 if has_pattern else 1)
