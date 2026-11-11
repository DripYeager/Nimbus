from __future__ import annotations

import pytest

from core.command_policy import asks_for_elevation, is_read_only


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
