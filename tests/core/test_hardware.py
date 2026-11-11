from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from core.hardware import BYTES_PER_GB, read_hardware


@pytest.fixture
def ram(mocker: MockerFixture) -> None:
    mocker.patch("core.hardware.psutil.virtual_memory", return_value=MagicMock(total=32 * BYTES_PER_GB))


def test_read_hardware_picks_the_card_with_the_most_memory(mocker: MockerFixture, ram: None) -> None:
    mocker.patch(
        "core.hardware._display_adapters",
        return_value=[("Intel UHD Graphics", 0.1), ("NVIDIA RTX 2000 Ada", 8.0)],
    )

    hardware = read_hardware()

    assert (hardware.ram_gb, hardware.gpu_name, hardware.vram_gb) == (32, "NVIDIA RTX 2000 Ada", 8.0)


def test_read_hardware_without_a_reported_card(mocker: MockerFixture, ram: None) -> None:
    mocker.patch("core.hardware._display_adapters", return_value=[])

    assert (read_hardware().gpu_name, read_hardware().vram_gb) == (None, 0.0)


def test_display_adapters_read_this_pc_without_admin() -> None:
    from core.hardware import _display_adapters

    assert all(isinstance(name, str) and size >= 0 for name, size in _display_adapters())
