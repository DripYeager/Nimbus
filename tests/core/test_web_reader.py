from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from core.web_reader import _html_to_text, check_address


def _resolves_to(mocker: MockerFixture, address: str) -> None:
    mocker.patch("core.web_reader.socket.getaddrinfo", return_value=[(0, 0, 0, "", (address, 0))])


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "ftp://example.com", "javascript:alert(1)", "http://"])
def test_check_address_allows_only_http_and_https(url: str) -> None:
    with pytest.raises(ToolError):
        check_address(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "192.168.1.1", "10.0.0.5", "169.254.1.1", "::1"])
def test_check_address_refuses_this_pc_and_the_local_network(mocker: MockerFixture, address: str) -> None:
    _resolves_to(mocker, address)

    with pytest.raises(ToolError, match="local network"):
        check_address("http://sneaky.example/")


def test_check_address_allows_a_public_site(mocker: MockerFixture) -> None:
    _resolves_to(mocker, "93.184.215.14")

    check_address("https://example.com/")


def test_html_to_text_keeps_the_content_and_drops_the_noise() -> None:
    html = (
        "<html><head><title>Recipe</title><script>track()</script></head><body>"
        "<nav>Home | About</nav><main><h1>Banana bread</h1><p>Mix <b>three</b> bananas.</p></main>"
        "<footer>Copyright</footer></body></html>"
    )

    title, text = _html_to_text(html)

    assert title == "Recipe"
    assert "# Banana bread" in text and "**three**" in text
    assert "track()" not in text and "Home | About" not in text and "Copyright" not in text
