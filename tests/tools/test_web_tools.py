from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from core.web_reader import WebPage
from tools.registry import ToolRegistry
from tools.web_tools import WebToolbox, given_by_user, needs_approval

URL = "https://example.com/post"


@pytest.fixture
def reader(mocker: MockerFixture) -> Mock:
    page = WebPage(url=URL, title="A post", text="Body text", truncated=True)
    return mocker.patch("tools.web_tools.read_page", return_value=page)


def test_read_returns_title_address_and_text(reader: Mock) -> None:
    content = WebToolbox().read({"url": URL}).content

    assert content.startswith("# A post\nhttps://example.com/post") and "first part" in content


def test_read_needs_an_address(reader: Mock) -> None:
    with pytest.raises(ToolError):
        WebToolbox().read({"url": ""})


@pytest.mark.parametrize(
    ("url", "typed", "expected"),
    [
        (URL, f"summarize {URL} please", True),
        (URL + "/", f"summarize {URL}", True),
        ("HTTPS://EXAMPLE.COM/post", f"read {URL}", True),
        ("https://evil.example/?d=secret", f"summarize {URL}", False),
        (URL, "summarize the article", False),
    ],
)
def test_given_by_user_only_for_links_the_user_typed(url: str, typed: str, expected: bool) -> None:
    assert given_by_user(url, typed) is expected


def test_needs_approval_for_an_address_the_user_did_not_type() -> None:
    assert needs_approval({"url": "https://other.example"}, "summarize the doc") is True


def test_register_never_offers_always_allow() -> None:
    registry = ToolRegistry()
    WebToolbox().register(registry)

    assert registry.can_always_allow("read_web_page") is False
