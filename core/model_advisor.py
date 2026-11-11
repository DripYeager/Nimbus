"""
Suggests which local Ollama model fits this PC. The choice comes from a short, hand-picked
list, because what matters most for Nimbus (reliably calling tools) can't be measured from the
hardware: every model on it is good at tool calling. The hardware only decides how big a model
the PC runs comfortably: on the graphics card when its memory holds the model plus Nimbus's
context window, otherwise on the processor, where a smaller model keeps answers quick. It also
says whether the pick is already downloaded. Pure decision-making; reading the hardware is
core/hardware.py's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.hardware import HardwareProfile
from models.api import ModelRecommendation

# Room the 16K-token context and runtime need on top of the model's own weights.
CONTEXT_OVERHEAD_GB = 1.5
# Below this the "GPU" is integrated graphics or too small to be worth using.
MIN_USEFUL_VRAM_GB = 3.0


@dataclass(frozen=True)
class ModelChoice:
    model: str
    size_gb: float
    # Smallest total RAM for which this is the pick when there's no usable GPU (0: never on CPU).
    cpu_min_ram_gb: float
    strength: str


# Best first. All are tool-capable on Ollama; sizes are the download sizes.
MODEL_CHOICES: tuple[ModelChoice, ...] = (
    ModelChoice("qwen3:14b", 9.3, 0, "the strongest answers and tool use in this list"),
    ModelChoice("qwen3:8b", 5.2, 0, "strong answers and reliable tool use"),
    ModelChoice("qwen3:4b", 2.6, 8, "good tool use while staying quick"),
    ModelChoice("qwen3:1.7b", 1.4, 0, "runs on almost anything, but answers are simpler"),
)
FALLBACK = MODEL_CHOICES[-1]


def recommend_model(hardware: HardwareProfile, installed: list[str]) -> ModelRecommendation:
    """The model to suggest for this PC, with a plain-language reason."""
    choice, on_gpu = _best_fit(hardware)
    gpu = short_gpu_name(hardware.gpu_name or "")
    where = (
        f"Runs on your {gpu} ({hardware.vram_gb:.0f} GB), so answers come quickly." if on_gpu else _cpu_reason(hardware)
    )
    return ModelRecommendation(
        model=choice.model,
        size_gb=choice.size_gb,
        reason=f"{choice.strength.capitalize()}. {where}",
        hardware=describe_hardware(hardware),
        installed=any(_same_model(name, choice.model) for name in installed),
    )


def describe_hardware(hardware: HardwareProfile) -> str:
    """ "32 GB RAM · NVIDIA RTX 2000 Ada (8 GB)" or "16 GB RAM · no dedicated graphics"."""
    gpu = (
        f"{short_gpu_name(hardware.gpu_name)} ({hardware.vram_gb:.0f} GB)"
        if hardware.gpu_name and hardware.vram_gb >= MIN_USEFUL_VRAM_GB
        else "no dedicated graphics"
    )
    return f"{hardware.ram_gb:.0f} GB RAM · {gpu}"


def short_gpu_name(name: str) -> str:
    """ "NVIDIA RTX 2000 Ada Generation Laptop GPU" reads as "NVIDIA RTX 2000 Ada"."""
    trimmed = re.sub(r"\((R|TM)\)|\b(Generation|Laptop|GPU|Graphics)\b", "", name, flags=re.IGNORECASE)
    return " ".join(trimmed.split()) or name


def _best_fit(hardware: HardwareProfile) -> tuple[ModelChoice, bool]:
    """(choice, runs on the GPU): the stronger of what the graphics card holds whole and what
    the processor runs quickly. A small card shouldn't force a weaker model than the CPU manages
    (Ollama splits a model across both when it doesn't quite fit)."""
    gpu = _gpu_fit(hardware)
    cpu = _cpu_fit(hardware)
    if gpu is not None and MODEL_CHOICES.index(gpu) <= MODEL_CHOICES.index(cpu):
        return gpu, True
    return cpu, False


def _gpu_fit(hardware: HardwareProfile) -> ModelChoice | None:
    if hardware.vram_gb < MIN_USEFUL_VRAM_GB:
        return None
    return next((c for c in MODEL_CHOICES if c.size_gb + CONTEXT_OVERHEAD_GB <= hardware.vram_gb), None)


def _cpu_fit(hardware: HardwareProfile) -> ModelChoice:
    # Rounded, because "16 GB" machines report a little under 16 to the OS.
    ram = round(hardware.ram_gb)
    return next((c for c in MODEL_CHOICES if c.cpu_min_ram_gb and ram >= c.cpu_min_ram_gb), FALLBACK)


def _cpu_reason(hardware: HardwareProfile) -> str:
    return (
        f"Runs on your processor with {hardware.ram_gb:.0f} GB RAM; a bigger model would answer "
        "much more slowly without a graphics card."
    )


def _same_model(installed: str, wanted: str) -> bool:
    return installed.lower().removesuffix(":latest") == wanted.lower()
