"""
Fetches one web page the user pointed Nimbus at and turns it into readable text: the page's
title and main text as Markdown, without scripts, styles, menus or footers. Only http and https,
never addresses on this PC or the local network (no router pages, no Nimbus's own API), every
redirect checked the same way, and a size cap. Owns fetching and extraction only; when a
fetch needs the user's approval is the tool's business.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from core.exceptions import ToolError

TIMEOUT_S = 15.0
MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_TEXT_CHARS = 12_000
# An honest identity: the client's name, version and purpose. A site that turns automated
# readers away is respected; the tool then suggests opening the page in a browser.
USER_AGENT = "Nimbus/2.1 (Windows desktop assistant reading a page the user asked for)"
# Parts of a page that are never the content someone asked about.
NOISE_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe")
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    truncated: bool


def read_page(url: str) -> WebPage:
    """The page at url as title and Markdown text.

    Raises:
        ToolError: The address isn't allowed, the site can't be reached, or it isn't a web page.
    """
    current = url.strip()
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_address(current)
            response = _get(client, current)
            if response.status_code not in REDIRECT_CODES:
                return _to_page(current, response)
            current = urljoin(current, response.headers.get("location", ""))
    raise ToolError(f"{url} redirects too many times.")


def check_address(url: str) -> None:
    """Refuses anything but a public http(s) address.

    Raises:
        ToolError: Another scheme, no host, or a host on this PC or the local network.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError(f"Can only read http or https web pages, not {url!r}.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as e:
        raise ToolError(f"Couldn't find the site {parsed.hostname}.") from e
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ToolError(f"{parsed.hostname} points to this PC or the local network, which Nimbus doesn't read.")


def _get(client: httpx.Client, url: str) -> httpx.Response:
    """A GET that stops reading at MAX_BYTES."""
    try:
        with client.stream("GET", url) as response:
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            response._content = body[:MAX_BYTES]  # noqa: SLF001 - the capped body becomes the response's
            return response
    except httpx.HTTPError as e:
        raise ToolError(f"Couldn't load {url}: {e}") from e


def _to_page(url: str, response: httpx.Response) -> WebPage:
    if response.status_code in (401, 403, 429):
        raise ToolError(
            f"{url} doesn't allow automated reading ({response.status_code}). Open it in a browser instead."
        )
    if response.status_code >= 400:
        raise ToolError(f"{url} answered with error {response.status_code}.")
    kind = response.headers.get("content-type", "").lower()
    if "html" in kind:
        title, text = _html_to_text(response.text)
    elif kind.startswith("text/") or "json" in kind:
        title, text = url, response.text
    else:
        raise ToolError(f"{url} isn't a web page (it's {kind or 'an unknown type'}).")
    text = text.strip()
    return WebPage(url, title, text[:MAX_TEXT_CHARS], len(text) > MAX_TEXT_CHARS)


def _html_to_text(html: str) -> tuple[str, str]:
    """(title, Markdown of the main content). Prefers <main> or <article> when the page has one."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    markdown = markdownify(str(main), heading_style="ATX", strip=["img"])
    lines = [line.rstrip() for line in markdown.splitlines()]
    return title, "\n".join(line for i, line in enumerate(lines) if line or (i and lines[i - 1]))
