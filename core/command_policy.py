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

# Chaining, redirection, sub-expressions, script blocks, variables, escapes and line breaks: any
# of these could hide a second command inside an innocent-looking one. (";" is allowed because
# every statement it separates is checked on its own.)
_UNSAFE_CHARACTERS = re.compile(r"[&<>`$(){}@\r\n]|\|\|")
_ELEVATION = re.compile(r"-verb\s+runas|\brunas(\.exe)?\b|\bsudo\b|\bgsudo\b", re.IGNORECASE)
_SINGLE_QUOTED = re.compile(r"'[^']*'")
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
    # Double-quoted text expands $(...), so it gets no such pass. An unclosed quote fails here.
    structure = _SINGLE_QUOTED.sub("''", command)
    if "'" in structure.replace("''", "") or _UNSAFE_CHARACTERS.search(structure):
        return False
    statements = [statement for statement in structure.split(";") if statement.strip()]
    return bool(statements) and all(_statement_reads_only(statement) for statement in statements)


def _statement_reads_only(statement: str) -> bool:
    """One pipeline: an allow-listed first command, then only sorting, filtering and formatting."""
    segments = [segment.split() for segment in statement.split("|")]
    if any(not words for words in segments):
        return False
    first, *rest = segments
    if not _first_command_reads_only(first):
        return False
    return all(_name(words[0]) in _PIPE_FORMATTERS for words in rest)


def asks_for_elevation(command: str) -> bool:
    """True when command tries to run something as administrator."""
    return bool(_ELEVATION.search(command))


def _first_command_reads_only(words: list[str]) -> bool:
    name, args = _name(words[0]), [arg.strip("'\"") for arg in words[1:]]
    if name in _READ_ONLY_CMDLETS:
        return True
    rule = _READ_ONLY_TOOLS.get(name)
    return rule is not None and rule(args)


def _name(word: str) -> str:
    """The command's bare name: no quotes, no path, no ".exe"."""
    bare = word.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return bare.removesuffix(".exe")
