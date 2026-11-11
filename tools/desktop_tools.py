"""
Desktop tools: copy text to the clipboard, control music and volume, and list, switch to or
close app windows ("copy that as a table", "pause the music", "switch to Excel", "close
Spotify"). Only closing a window asks first; the rest are as harmless as pressing a key.
Owns the tools' wording; the Windows calls live in core/desktop_control.py.
"""

from __future__ import annotations

from typing import Any

from core import desktop_control
from core.exceptions import ToolError
from models.chat import ToolResult
from tools.registry import Tool, ToolRegistry, integer_param, object_schema, string_param, tool_spec

COPY = tool_spec(
    "copy_to_clipboard",
    "Put text on the clipboard so the user can paste it anywhere (an answer, a table in Markdown, an email draft).",
    object_schema({"text": string_param("Exactly the text to copy")}, ["text"]),
)
MEDIA = tool_spec(
    "media_control",
    "Control music and video like the keyboard's media keys: play_pause, next, previous, stop, mute, "
    "volume_up, volume_down. Works with whatever is playing (Spotify, a browser...).",
    object_schema(
        {
            "action": string_param("play_pause, next, previous, stop, mute, volume_up or volume_down"),
            "times": integer_param("For volume_up/volume_down: how many 2% steps (default 5)"),
        },
        ["action"],
    ),
)
SET_VOLUME = tool_spec(
    "set_volume",
    "Set the PC's volume to a percentage (0 to 100).",
    object_schema({"percent": integer_param("Volume from 0 to 100")}, ["percent"]),
)
LIST_WINDOWS = tool_spec("list_open_windows", "List the app windows open on the PC.", object_schema({}))
SWITCH = tool_spec(
    "switch_to_window",
    "Bring an open app window to the front, by program or title (e.g. excel, chrome, budget.xlsx).",
    object_schema({"name": string_param("Program name or part of the window title")}, ["name"]),
)
CLOSE = tool_spec(
    "close_window",
    "Close an open app window, like clicking its X (the app still asks to save unsaved work).",
    object_schema({"name": string_param("Program name or part of the window title")}, ["name"]),
)
DEFAULT_VOLUME_STEPS = 5


class DesktopToolbox:
    def register(self, registry: ToolRegistry) -> None:
        for tool in (
            Tool(COPY, self.copy, lambda a: "Copied to the clipboard"),
            Tool(MEDIA, self.media, lambda a: f"Media: {str(a.get('action', '')).replace('_', ' ')}"),
            Tool(SET_VOLUME, self.volume, lambda a: f"Set the volume to {a.get('percent')}%"),
            Tool(LIST_WINDOWS, self.list_windows, lambda a: "Listed open windows"),
            Tool(SWITCH, self.switch, lambda a: f"Switch to {a.get('name', '')}"),
            Tool(CLOSE, self.close, lambda a: f"Close {a.get('name', '')}", requires_confirmation=True),
        ):
            registry.register(tool)

    def copy(self, args: dict[str, Any]) -> ToolResult:
        text = str(args.get("text", ""))
        if not text.strip():
            raise ToolError("There's nothing to copy.")
        desktop_control.copy_text(text)
        return ToolResult(content=f"Copied {len(text):,} characters to the clipboard.")

    def media(self, args: dict[str, Any]) -> ToolResult:
        action = str(args.get("action", "")).strip().lower()
        times = int(args.get("times") or DEFAULT_VOLUME_STEPS) if action.startswith("volume") else 1
        desktop_control.press_media_key(action, times)
        return ToolResult(content=f"Pressed {action.replace('_', ' ')}" + (f" {times} times." if times > 1 else "."))

    def volume(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=f"Volume set to about {desktop_control.set_volume(int(args['percent']))}%.")

    def list_windows(self, args: dict[str, Any]) -> ToolResult:
        windows = desktop_control.open_windows()
        if not windows:
            return ToolResult(content="No app windows are open.")
        return ToolResult(content="\n".join(f"- {w.program}: {w.title}" for w in windows))

    def switch(self, args: dict[str, Any]) -> ToolResult:
        window = desktop_control.find_window(str(args["name"]))
        desktop_control.switch_to(window)
        return ToolResult(content=f"Switched to {window.program} ({window.title}).")

    def close(self, args: dict[str, Any]) -> ToolResult:
        window = desktop_control.find_window(str(args["name"]))
        desktop_control.close(window)
        return ToolResult(content=f"Asked {window.program} ({window.title}) to close.")
