"""
The catalogue of tools the assistant may call: each tool's model-facing spec, the function that
runs it, whether it needs the user's go-ahead first, and how to describe a call in plain words.
Owns lookup and safe execution only — the tools themselves live in their own modules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.exceptions import NimbusError
from core.logger import get_logger
from models.chat import ToolCall, ToolResult, ToolSpec

logger = get_logger(__name__)

ToolHandler = Callable[[dict[str, Any]], ToolResult]
CallDescriber = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    """One callable capability. Action tools (anything that launches or writes) set
    requires_confirmation, and describe() is what the confirmation card shows."""

    spec: ToolSpec
    handler: ToolHandler
    describe: CallDescriber
    requires_confirmation: bool = False


class ToolRegistry:
    """Name -> Tool lookup plus error-safe execution."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Adds tool; a duplicate name is a wiring bug, so it fails loudly."""
        if tool.spec.name in self._tools:
            raise ValueError(f"A tool named {tool.spec.name!r} is already registered.")
        self._tools[tool.spec.name] = tool

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def execute(self, call: ToolCall) -> ToolResult:
        """Runs call. Failures come back as an error result rather than an exception, so the
        model can read what went wrong and try something else."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(content=f"There's no tool called {call.name!r}.", is_error=True)
        try:
            return tool.handler(call.arguments)
        except (NimbusError, KeyError, TypeError, ValueError, OSError, OverflowError) as e:
            logger.warning("Tool call failed", extra={"tool": call.name, "error": str(e)})
            return ToolResult(content=f"{call.name} failed: {e}", is_error=True)
        except Exception as e:
            # A bug in one tool shouldn't end the whole answer; log the trace and let the model
            # tell the user that step failed.
            logger.exception("Tool crashed", extra={"tool": call.name})
            return ToolResult(content=f"{call.name} hit an unexpected error: {type(e).__name__}", is_error=True)

    def describe_call(self, call: ToolCall) -> str:
        """Plain-language summary of call, for chips and confirmation cards."""
        tool = self._tools.get(call.name)
        if tool is None:
            return call.name
        try:
            return tool.describe(call.arguments)
        except (KeyError, TypeError, ValueError):
            return call.name


def tool_spec(name: str, description: str, parameters: dict[str, Any]) -> ToolSpec:
    """Shorthand used by the toolboxes when declaring their tools."""
    return ToolSpec(name=name, description=description, parameters=parameters)


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    """Builds the JSON-schema object every tool's parameters take."""
    return {"type": "object", "properties": properties, "required": required or []}


def string_param(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def integer_param(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def file_name_arg(args: dict[str, Any]) -> str:
    """The file name from a call's "path" argument, for short chip labels."""
    return Path(str(args.get("path", ""))).name or "a file"
