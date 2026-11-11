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
# The well-known NAT64 range: its last 32 bits are an IPv4 address.
NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
IPV4_BITS = 0xFFFFFFFF
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
            address = check_address(current)
            response = _get(client, current, address)
            if response.status_code not in REDIRECT_CODES:
                return _to_page(current, response)
            current = urljoin(current, response.headers.get("location", ""))
    raise ToolError(f"{url} redirects too many times.")


def check_address(url: str) -> str:
    """Refuses anything but a public http(s) address; returns the checked IP address, which the
    request then connects to, so a second lookup can't swap in a local one (DNS rebinding).

    Raises:
        ToolError: Another scheme, no host, or a host on this PC or the local network.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError(f"Can only read http or https web pages, not {url!r}.")
    try:
        addresses = [info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)]
    except socket.gaierror as e:
        raise ToolError(f"Couldn't find the site {parsed.hostname}.") from e
    for address in addresses:
        if _is_local_address(address):
            raise ToolError(f"{parsed.hostname} points to this PC or the local network, which Nimbus doesn't read.")
    if not addresses:
        raise ToolError(f"Couldn't find the site {parsed.hostname}.")
    return addresses[0].split("%")[0]


def _is_local_address(address: str) -> bool:
    """True for anything that isn't a public internet address: this PC, the local network,
    shared and reserved ranges, multicast, and an IPv4 address hidden inside an IPv6 one
    ("::ffff:127.0.0.1", NAT64 "64:ff9b::7f00:1", 6to4 "2002:7f00:1::")."""
    ip = ipaddress.ip_address(address.split("%")[0])
    candidates = [ip]
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            candidates = [ip.ipv4_mapped]
        elif ip.sixtofour is not None:
            candidates.append(ip.sixtofour)
        elif ip in NAT64_PREFIX:
            candidates.append(ipaddress.IPv4Address(int(ip) & IPV4_BITS))
    return any(not candidate.is_global or candidate.is_multicast for candidate in candidates)


def _get(client: httpx.Client, url: str, address: str) -> httpx.Response:
    """A GET to the checked address that stops reading at MAX_BYTES. The site's own name still
    goes in the Host header and the TLS handshake, so its certificate is verified as usual."""
    parsed = urlparse(url)
    host = f"[{address}]" if ":" in address else address
    pinned = parsed._replace(netloc=host + (f":{parsed.port}" if parsed.port else "")).geturl()
    site = parsed.netloc.rsplit("@", 1)[-1]
    try:
        with client.stream(
            "GET", pinned, headers={"Host": site}, extensions={"sni_hostname": parsed.hostname}
        ) as response:
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
