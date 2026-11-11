from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from core.process_monitor import BYTES_PER_MB, ProgramUsage, busiest_programs, describe_usage


def _process(name: str, cpu: float, memory_mb: float) -> MagicMock:
    process = MagicMock(info={"name": name})
    process.cpu_percent.return_value = cpu
    process.memory_info.return_value = MagicMock(rss=memory_mb * BYTES_PER_MB)
    return process


@pytest.fixture
def machine(mocker: MockerFixture) -> None:
    processes = [
        _process("Code.exe", 20.0, 300),
        _process("Code.exe", 10.0, 200),
        _process("System Idle Process", 300.0, 0),
        _process("chrome.exe", 4.0, 900),
    ]
    mocker.patch("core.process_monitor.psutil.process_iter", return_value=processes)
    mocker.patch("core.process_monitor.psutil.cpu_count", return_value=2)
    mocker.patch("core.process_monitor.time.sleep")


def test_busiest_programs_adds_up_a_programs_processes(machine: None) -> None:
    programs = {p.name: p for p in busiest_programs()}

    assert programs["Code"] == ProgramUsage("Code", cpu_percent=15.0, memory_mb=500, processes=2)


def test_busiest_programs_leaves_out_the_idle_entry(machine: None) -> None:
    assert "System Idle Process" not in {p.name for p in busiest_programs()}


def test_describe_usage_lists_cpu_and_memory_leaders(mocker: MockerFixture) -> None:
    mocker.patch("core.process_monitor.psutil.cpu_percent", return_value=37.0)
    mocker.patch(
        "core.process_monitor.psutil.virtual_memory",
        return_value=MagicMock(percent=60.0, used=12 * 1024 * BYTES_PER_MB, total=32 * 1024 * BYTES_PER_MB),
    )
    programs = [ProgramUsage("Code", 15.0, 500, 2), ProgramUsage("chrome", 2.0, 900, 1)]

    text = describe_usage(programs)

    assert "CPU 37% busy" in text
    assert text.index("- Code: 15.0% (2 processes)") < text.index("- chrome: 2.0%")
    assert text.index("- chrome: 900 MB") < text.index("- Code: 500 MB")
