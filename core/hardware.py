"""
Reads the two facts that decide which local model a PC can run well: total RAM, and the
graphics card with the most dedicated memory (VRAM). VRAM comes from the display driver's
registry entry (HardwareInformation.qwMemorySize), which is readable without admin rights and,
unlike WMI's AdapterRAM, isn't capped at 4 GB. Read-only; choosing a model is model_advisor's job.
"""

from __future__ import annotations

import sys
import winreg
from dataclasses import dataclass

import psutil

from core.logger import get_logger

logger = get_logger(__name__)

DISPLAY_ADAPTERS_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
VRAM_VALUE = "HardwareInformation.qwMemorySize"
BYTES_PER_GB = 1024**3


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: float
    gpu_name: str | None = None
    vram_gb: float = 0.0


def read_hardware() -> HardwareProfile:
    """This PC's RAM and its biggest graphics card (integrated graphics report little or none)."""
    ram_gb = psutil.virtual_memory().total / BYTES_PER_GB
    adapters = _display_adapters() if sys.platform == "win32" else []
    if not adapters:
        return HardwareProfile(ram_gb=ram_gb)
    name, vram = max(adapters, key=lambda adapter: adapter[1])
    return HardwareProfile(ram_gb=ram_gb, gpu_name=name, vram_gb=vram)


def _display_adapters() -> list[tuple[str, float]]:
    """(name, VRAM in GB) for each display adapter the driver reports a memory size for."""
    adapters: list[tuple[str, float]] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_ADAPTERS_KEY) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                name = winreg.EnumKey(root, index)
                if name.isdigit():
                    adapter = _read_adapter(root, name)
                    if adapter is not None:
                        adapters.append(adapter)
    except OSError as e:
        logger.warning("Couldn't read the graphics adapters", extra={"error": str(e)})
    return adapters


def _read_adapter(root: winreg.HKEYType, name: str) -> tuple[str, float] | None:
    try:
        with winreg.OpenKey(root, name) as key:
            description = str(winreg.QueryValueEx(key, "DriverDesc")[0])
            memory = winreg.QueryValueEx(key, VRAM_VALUE)[0]
    except OSError:
        return None
    vram_gb = _vram_gb(memory)
    if vram_gb is None:
        return None
    return description, vram_gb


def _vram_gb(memory: object) -> float | None:
    """Gigabytes from a registry memory value: a QWORD, or the raw bytes some older drivers write.
    None when the value isn't a size, so one odd adapter can't sink the whole readout."""
    try:
        size = int.from_bytes(memory, "little") if isinstance(memory, bytes) else int(memory)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    return size / BYTES_PER_GB
