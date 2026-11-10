"""
Parses Server-Sent Events frames, "event: name" and "data: json" lines separated by blank
lines, into (event_name, payload) pairs. Pure text parsing; knows nothing about HTTP
transport, Qt, or what any payload means.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

DEFAULT_EVENT_NAME = "message"


def parse_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, dict[str, object]]]:
    """Groups raw SSE lines into (event_name, parsed_json_payload) pairs, one per "data:" line."""
    event_name = DEFAULT_EVENT_NAME
    for line in lines:
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            yield event_name, json.loads(line.removeprefix("data:").strip())
            event_name = DEFAULT_EVENT_NAME
