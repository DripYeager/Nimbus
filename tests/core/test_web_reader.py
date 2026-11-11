from __future__ import annotations

import httpx
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ToolError
from core.web_reader import _html_to_text, check_address, read_page


def _resolves_to(mocker: MockerFixture, address: str) -> None:
    mocker.patch("core.web_reader.socket.getaddrinfo", return_value=[(0, 0, 0, "", (address, 0))])


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "ftp://example.com", "javascript:alert(1)", "http://"])
def test_check_address_allows_only_http_and_https(url: str) -> None:
    with pytest.raises(ToolError):
        check_address(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "192.168.1.1",
        "10.0.0.5",
        "169.254.1.1",
        "::1",
        "::ffff:127.0.0.1",
        "::ffff:192.168.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "198.18.0.1",
        "fd00::1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::1",
        "ff0e::1",
    ],
)
def test_check_address_refuses_this_pc_and_the_local_network(mocker: MockerFixture, address: str) -> None:
    _resolves_to(mocker, address)

    with pytest.raises(ToolError, match="local network"):
        check_address("http://sneaky.example/")


@pytest.mark.parametrize("address", ["93.184.215.14", "::ffff:93.184.215.14", "2606:4700::1111", "64:ff9b::808:808"])
def test_check_address_allows_a_public_site(mocker: MockerFixture, address: str) -> None:
    _resolves_to(mocker, address)

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


def test_read_page_connects_to_the_address_it_checked(mocker: MockerFixture) -> None:
    """A second DNS lookup can't swap in a local address: the request goes to the checked IP,
    with the site's own name in the Host header and the TLS server name."""
    _resolves_to(mocker, "93.184.215.14")
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, html="<title>Example</title><main>Hello</main>")

    real_client = httpx.Client
    mocker.patch("core.web_reader.httpx.Client", lambda **kw: real_client(transport=httpx.MockTransport(answer), **kw))

    page = read_page("https://example.com/post?id=1")

    request = seen[0]
    assert request.url.host == "93.184.215.14" and request.url.path == "/post"
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"
    assert page.url == "https://example.com/post?id=1" and page.title == "Example"
