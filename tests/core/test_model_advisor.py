from __future__ import annotations

import pytest

from core.hardware import HardwareProfile
from core.model_advisor import describe_hardware, recommend_model, short_gpu_name

RTX_8GB = HardwareProfile(ram_gb=31.7, gpu_name="NVIDIA RTX 2000 Ada", vram_gb=8.0)


@pytest.mark.parametrize(
    ("hardware", "expected"),
    [
        (HardwareProfile(ram_gb=64, gpu_name="NVIDIA RTX 4090", vram_gb=24), "qwen3:14b"),
        (RTX_8GB, "qwen3:8b"),
        (HardwareProfile(ram_gb=16, gpu_name="NVIDIA GTX 1650", vram_gb=4), "qwen3:4b"),
        (HardwareProfile(ram_gb=15.7, gpu_name="Intel UHD Graphics", vram_gb=0.5), "qwen3:4b"),
        (HardwareProfile(ram_gb=7.8), "qwen3:4b"),
        (HardwareProfile(ram_gb=4), "qwen3:1.7b"),
    ],
)
def test_recommend_model_fits_the_hardware(hardware: HardwareProfile, expected: str) -> None:
    assert recommend_model(hardware, []).model == expected


def test_recommend_model_explains_a_gpu_pick() -> None:
    recommendation = recommend_model(RTX_8GB, [])

    assert "NVIDIA RTX 2000 Ada (8 GB)" in recommendation.reason


def test_recommend_model_explains_a_processor_pick() -> None:
    assert "processor" in recommend_model(HardwareProfile(ram_gb=16), []).reason


def test_recommend_model_notices_it_is_already_downloaded() -> None:
    assert recommend_model(RTX_8GB, ["llama3.1:8b", "qwen3:8b"]).installed is True


def test_recommend_model_matches_a_latest_tag() -> None:
    assert recommend_model(HardwareProfile(ram_gb=4), ["qwen3:1.7b:latest"]).installed is True


def test_describe_hardware_ignores_integrated_graphics() -> None:
    hardware = HardwareProfile(ram_gb=15.7, gpu_name="Intel UHD Graphics", vram_gb=0.5)

    assert describe_hardware(hardware) == "16 GB RAM · no dedicated graphics"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("NVIDIA RTX 2000 Ada Generation Laptop GPU", "NVIDIA RTX 2000 Ada"),
        ("Intel(R) UHD Graphics", "Intel UHD"),
        ("AMD Radeon RX 7600", "AMD Radeon RX 7600"),
    ],
)
def test_short_gpu_name_drops_marketing_words(name: str, expected: str) -> None:
    assert short_gpu_name(name) == expected
