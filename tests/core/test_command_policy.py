from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.command_policy import asks_for_elevation, is_read_only
from core.command_text import blank_single_quoted


@pytest.mark.parametrize(
    "command",
    [
        "ipconfig",
        "ipconfig /all",
        "systeminfo",
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5",
        "Get-Volume",
        "ping 8.8.8.8 -n 2",
        "netsh wlan show interfaces",
        "winget list",
        "Get-Process | Where-Object CPU -gt 100",
        "systeminfo | findstr Memory",
        r"C:\Windows\System32\ipconfig.exe /all",
        "GET-PROCESS -Name chrome",
        "Test-NetConnection github.com -Port 443",
        "route print",
        "arp -a",
        "ipconfig /all; netsh wlan show interfaces",
        r"Get-Counter '\Process(*)\% Processor Time'",
        "Get-Process 'x; Remove-Item y'",
        "ipconfig.exe /all",
        "ipconfig /all | findstr /i ipv4",
        'ipconfig /all | findstr /c:"IPv4 Address"',
        'systeminfo | findstr /b /c:"OS Name"',
        # One word after findstr is what it searches for, not a file it opens.
        r"systeminfo | findstr 'C:\Windows\win.ini'",
        r"Get-Process | C:\Windows\System32\findstr.exe chrome",
        "Get-Process | Select-String chrome",
        "Get-Service | Select-String -Pattern wlan",
        "Get-Process | Select-String -Patt chrome -SimpleMatch",
    ],
)
def test_is_read_only_lets_information_commands_run(command: str) -> None:
    assert is_read_only(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "",
        "ipconfig /release",
        "ipconfig /flushdns",
        "Get-Process | Stop-Process",
        "netsh wlan set hostednetwork mode=allow",
        "netsh interface set interface Wi-Fi disable",
        "winget install vlc",
        "Remove-Item x",
        "Get-ChildItem C:\\",
        "Get-Content secrets.txt",
        "Get-Process; Remove-Item x",
        "Get-Process && Remove-Item x",
        "Get-Process || Remove-Item x",
        "Get-Process | Where-Object { $_.CPU -gt 1 }",
        "Get-Process $(Remove-Item x)",
        "Get-Process > out.txt",
        "Get-Process `\nRemove-Item x",
        "Get-Process | Out-File out.txt",
        "Get-Process |",
        "route add 0.0.0.0 mask 0.0.0.0 10.0.0.1",
        "arp -d *",
        "powercfg /batteryreport",
        "Start-Process cmd -Verb RunAs",
        "ipconfig; Remove-Item x",
        "Get-Process 'unclosed",
        'Get-Process "$(Remove-Item y)"',
        "Get-Process ''; Remove-Item x",
        r"C:\Users\Public\systeminfo.exe",
        r"C:\Windows\System32\..\..\Users\Public\systeminfo.exe",
        "Get-Process | sort.exe",
        r"systeminfo | findstr Memory C:\Windows\win.ini",
        r"Get-Date | Select-String -Path C:\secret.txt",
        # A program named like a tool, anywhere but directly in System32 or SysWOW64.
        r"C:\Windows\Temp\ipconfig.exe /all",
        r"C:\Windows\System32\Tasks\ipconfig.exe",
        r".\ipconfig.exe",
        "./systeminfo",
        # Lookalike programs after a pipe, and findstr or Select-String opening a file.
        r"Get-Process | C:\Windows\System32\sort.exe",
        "Get-Process | where.exe x",
        "Get-Process | findstr x secrets.txt",
        r"Get-Process | findstr /g:C:\patterns.txt",
        "Get-Process | findstr /f:list.txt x",
        'Get-Process | findstr /c:"x" secrets.txt',
        "Get-Process | Select-String -pa x",
        "Get-Process | Select-String foo secrets.txt",
        r"Get-Process | Select-String foo 'C:\secret.txt'",
        "Get-Process | Select-String -LiteralPath:secrets.txt foo",
        "Get-Process | Select-String -Pattern x secrets.txt",
        # A ' inside double quotes is literal, so it can't hide a $(...) between two of them.
        'hostname "\'" $(New-Item pwned.txt) "\'"',
        "Get-Process \u2018x\u2019; Remove-Item y",
        r"Get-Date | C:\Windows\System32\sort /O out.txt",
        r"Get-Date | C:\Windows\System32\sort C:\Windows\win.ini",
        "Get-Date | findstr -f:list.txt",
        r"Get-Date | findstr -g:C:\patterns.txt x",
    ],
)
def test_is_read_only_holds_back_anything_that_could_change_something(command: str) -> None:
    assert is_read_only(command) is False


@pytest.mark.parametrize(
    "command", ["Start-Process powershell -Verb RunAs", "runas /user:Administrator cmd", "sudo winget install x"]
)
def test_asks_for_elevation_spots_requests_for_admin_rights(command: str) -> None:
    assert asks_for_elevation(command) is True


def test_asks_for_elevation_leaves_ordinary_commands_alone() -> None:
    assert asks_for_elevation("Get-Process") is False


def test_is_read_only_wants_windows_own_tool_first_on_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "hostname.exe").write_bytes(b"")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert is_read_only("hostname") is False
    assert is_read_only("Get-Process") is True


def test_blank_single_quoted_reads_quotes_left_to_right() -> None:
    assert blank_single_quoted("x 'a $(b)' y") == "x '' y"
    assert blank_single_quoted('x "\'" $(y) "\'"') == 'x "_" $(y) "_"'
    assert blank_single_quoted("x 'open") is None
    assert blank_single_quoted("x “y”") is None
