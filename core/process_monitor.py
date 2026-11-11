"""
What's using the PC right now: samples every process's processor use over a short window and
reports the busiest programs by CPU share and by memory, with a program's helper processes
(a browser's tabs, an editor's extensions) added together. Read-only; never touches a process.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil

DEFAULT_SAMPLE_S = 1.0
DEFAULT_LIMIT = 8
BYTES_PER_MB = 1024 * 1024
# Not a program: the share of processor time nothing used.
IGNORED_NAMES = frozenset({"system idle process"})


@dataclass(frozen=True)
class ProgramUsage:
    name: str
    cpu_percent: float
    memory_mb: float
    processes: int


def busiest_programs(sample_s: float = DEFAULT_SAMPLE_S) -> list[ProgramUsage]:
    """Every program's CPU share (of the whole machine) and memory, measured over sample_s.

    Also starts the machine-wide CPU window: the first reading is always zero, so this call
    happens before the wait and describe_usage reads it afterwards.
    """
    psutil.cpu_percent(None)
    processes = list(psutil.process_iter(["name"]))
    for process in processes:
        try:
            process.cpu_percent(None)
        except psutil.Error:
            continue
    time.sleep(sample_s)
    cores = psutil.cpu_count() or 1
    totals: dict[str, list[float]] = {}
    for process in processes:
        try:
            name = process.info["name"] or "unknown"
            cpu, memory = process.cpu_percent(None) / cores, process.memory_info().rss / BYTES_PER_MB
        except psutil.Error:
            continue
        if name.lower() in IGNORED_NAMES:
            continue
        entry = totals.setdefault(name.removesuffix(".exe"), [0.0, 0.0, 0])
        entry[0], entry[1], entry[2] = entry[0] + cpu, entry[1] + memory, entry[2] + 1
    return [ProgramUsage(name, cpu, memory, int(count)) for name, (cpu, memory, count) in totals.items()]


def describe_usage(programs: list[ProgramUsage], limit: int = DEFAULT_LIMIT) -> str:
    """Two short tables: the busiest programs by CPU, then by memory."""
    by_cpu = sorted(programs, key=lambda p: p.cpu_percent, reverse=True)[:limit]
    by_memory = sorted(programs, key=lambda p: p.memory_mb, reverse=True)[:limit]
    total_cpu = psutil.cpu_percent(None)
    memory = psutil.virtual_memory()
    lines = [
        f"Whole PC: CPU {total_cpu:.0f}% busy, memory {memory.percent:.0f}% used "
        f"({memory.used / BYTES_PER_MB / 1024:.1f} of {memory.total / BYTES_PER_MB / 1024:.1f} GB).",
        "",
        "Busiest by CPU (share of the whole processor, over the last second):",
        *[f"- {p.name}: {p.cpu_percent:.1f}%{_count(p)}" for p in by_cpu],
        "",
        "Biggest by memory:",
        *[f"- {p.name}: {p.memory_mb:,.0f} MB{_count(p)}" for p in by_memory],
    ]
    return "\n".join(lines)


def _count(program: ProgramUsage) -> str:
    return f" ({program.processes} processes)" if program.processes > 1 else ""
