"""
The read_web_page tool: reads one web page the user points Nimbus at ("summarize this link").
A link the user typed in their message is fetched straight away; any other address (one the
model found in a document, say) waits for approval every time, because a crafted page or file
could otherwise make Nimbus send data to a site inside a URL. Owns that rule and the tool's
wording; fetching lives in core/web_reader.py.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ToolError
from core.web_reader import read_page
from models.chat import ToolResult
from tools.registry import Tool, ToolRegistry, object_schema, string_param, tool_spec

READ_WEB_PAGE = tool_spec(
    "read_web_page",
    "Read the text of a web page (http or https) to summarize it or answer questions about it. Use it for links "
    "the user gives. It can't log in, and some sites refuse automated reading.",
    object_schema({"url": string_param("The full address, starting with http:// or https://")}, ["url"]),
)


class WebToolbox:
    def register(self, registry: ToolRegistry) -> None:
        registry.register(
            Tool(READ_WEB_PAGE, self.read, describe_read, confirm_when=needs_approval, always_allowable=False)
        )

    def read(self, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url", "")).strip()
        if not url:
            raise ToolError("No address was given.")
        page = read_page(url)
        note = "\n\n[The page was longer; this is the first part.]" if page.truncated else ""
        return ToolResult(content=f"# {page.title or page.url}\n{page.url}\n\n{page.text}{note}")


def needs_approval(args: dict[str, Any], user_text: str) -> bool:
    """Free only when the user typed this address themselves in their latest message."""
    return not given_by_user(str(args.get("url", "")), user_text)


def given_by_user(url: str, user_text: str) -> bool:
    """True when url appears in what the user typed (ignoring case and a trailing slash)."""
    wanted = url.strip().rstrip("/").lower()
    return bool(wanted) and wanted in user_text.lower()


def describe_read(args: dict[str, Any]) -> str:
    return f"Read the web page {str(args.get('url', '')).strip()}"
