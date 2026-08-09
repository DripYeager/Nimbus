from __future__ import annotations

from core.sse import parse_sse_events


def test_parse_sse_events_pairs_event_name_with_its_data() -> None:
    lines = ["event: token", 'data: {"text": "hello"}', "", "event: done", 'data: {"used_llm": true}']

    events = list(parse_sse_events(lines))

    assert events == [("token", {"text": "hello"}), ("done", {"used_llm": True})]


def test_parse_sse_events_defaults_to_message_when_no_event_name_is_given() -> None:
    lines = ['data: {"answer": "hi"}']

    events = list(parse_sse_events(lines))

    assert events == [("message", {"answer": "hi"})]


def test_parse_sse_events_resets_the_event_name_after_each_data_line() -> None:
    lines = ["event: token", 'data: {"a": 1}', 'data: {"b": 2}']

    events = list(parse_sse_events(lines))

    assert events == [("token", {"a": 1}), ("message", {"b": 2})]


def test_parse_sse_events_returns_nothing_for_an_empty_stream() -> None:
    assert list(parse_sse_events([])) == []
