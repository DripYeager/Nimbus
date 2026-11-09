from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from core.usage_meter import UsageMeter


@pytest.fixture
def usage_file(tmp_path: Path) -> Path:
    return tmp_path / "data" / "usage.json"


def test_calls_today_is_zero_before_any_call(usage_file: Path) -> None:
    assert UsageMeter(usage_file).calls_today() == 0


def test_record_call_increments_todays_count(usage_file: Path) -> None:
    meter = UsageMeter(usage_file)

    meter.record_call()
    meter.record_call()

    assert meter.calls_today() == 2


def test_record_call_persists_across_restarts(usage_file: Path) -> None:
    UsageMeter(usage_file).record_call()

    assert UsageMeter(usage_file).calls_today() == 1


def test_calls_today_ignores_a_count_from_an_earlier_day(usage_file: Path) -> None:
    usage_file.parent.mkdir(parents=True)
    usage_file.write_text(json.dumps({"date": "2020-01-01", "count": 41}), encoding="utf-8")

    assert UsageMeter(usage_file).calls_today() == 0


def test_record_call_starts_a_new_day_at_one(usage_file: Path) -> None:
    usage_file.parent.mkdir(parents=True)
    usage_file.write_text(json.dumps({"date": "2020-01-01", "count": 41}), encoding="utf-8")

    UsageMeter(usage_file).record_call()

    assert json.loads(usage_file.read_text(encoding="utf-8")) == {"date": date.today().isoformat(), "count": 1}


def test_calls_today_starts_over_when_the_file_is_corrupt(usage_file: Path, caplog: pytest.LogCaptureFixture) -> None:
    usage_file.parent.mkdir(parents=True)
    usage_file.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert UsageMeter(usage_file).calls_today() == 0
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_record_call_logs_rather_than_raises_when_it_cannot_save(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    unwritable = tmp_path / "is-a-folder"
    unwritable.mkdir()

    with caplog.at_level(logging.WARNING):
        UsageMeter(unwritable).record_call()

    assert any("usage count" in record.getMessage() for record in caplog.records)
