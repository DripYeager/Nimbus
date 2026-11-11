from __future__ import annotations

from typing import Any

import pytest

from core.exceptions import ToolError
from models.chat import ToolCall, ToolResult, ToolSpec
from tools.registry import Tool, ToolRegistry, approval_group, file_name_arg, object_schema, string_param, tool_spec


def _tool(name: str, handler: Any = None, describe: Any = None, requires_confirmation: bool = False) -> Tool:
    return Tool(
        tool_spec(name, f"The {name} tool", object_schema({"path": string_param("A path")}, ["path"])),
        handler or (lambda args: ToolResult(content=f"ran {name}")),
        describe or (lambda args: f"Ran {name}"),
        requires_confirmation,
    )


def _raise(error: Exception) -> Any:
    def handler(args: dict[str, Any]) -> ToolResult:
        raise error

    return handler


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_tool("alpha"))
    registry.register(_tool("beta", requires_confirmation=True))
    return registry


def test_register_makes_the_tool_available(registry: ToolRegistry) -> None:
    assert registry.names() == ["alpha", "beta"]
    assert registry.get("beta").requires_confirmation is True


def test_register_raises_on_a_duplicate_name(registry: ToolRegistry) -> None:
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_tool("alpha"))


def test_get_returns_none_for_an_unknown_tool(registry: ToolRegistry) -> None:
    assert registry.get("gamma") is None


def test_specs_lists_every_tool_spec(registry: ToolRegistry) -> None:
    assert [spec.name for spec in registry.specs()] == ["alpha", "beta"]


def test_execute_runs_the_handler_with_the_call_arguments() -> None:
    seen: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register(_tool("echo", lambda args: seen.append(args) or ToolResult(content="ok")))

    result = registry.execute(ToolCall(id="c1", name="echo", arguments={"path": "a.txt"}))

    assert result == ToolResult(content="ok")
    assert seen == [{"path": "a.txt"}]


def test_execute_returns_an_error_result_for_an_unknown_tool(registry: ToolRegistry) -> None:
    result = registry.execute(ToolCall(id="c1", name="gamma"))

    assert result.is_error is True
    assert "gamma" in result.content


@pytest.mark.parametrize("error", [ToolError("bad path"), KeyError("path"), TypeError("nope"), ValueError("not int")])
def test_execute_turns_handler_failures_into_error_results(error: Exception) -> None:
    registry = ToolRegistry()
    registry.register(_tool("fragile", _raise(error)))

    result = registry.execute(ToolCall(id="c1", name="fragile"))

    assert result.is_error is True
    assert result.content.startswith("fragile failed:")


def test_execute_turns_an_unexpected_crash_into_an_error_result() -> None:
    registry = ToolRegistry()
    registry.register(_tool("buggy", _raise(RuntimeError("bug"))))

    result = registry.execute(ToolCall(id="c1", name="buggy"))

    assert result.is_error
    assert "RuntimeError" in result.content


def test_execute_turns_an_os_error_into_an_error_result() -> None:
    registry = ToolRegistry()
    registry.register(_tool("disk", _raise(OSError("drive not ready"))))

    assert registry.execute(ToolCall(id="c1", name="disk")).is_error


def test_describe_call_uses_the_tool_description(registry: ToolRegistry) -> None:
    assert registry.describe_call(ToolCall(id="c1", name="alpha")) == "Ran alpha"


def test_describe_call_falls_back_to_the_name_for_an_unknown_tool(registry: ToolRegistry) -> None:
    assert registry.describe_call(ToolCall(id="c1", name="gamma")) == "gamma"


def test_describe_call_falls_back_to_the_name_when_describing_fails() -> None:
    registry = ToolRegistry()
    registry.register(_tool("odd", describe=lambda args: args["missing"]))

    assert registry.describe_call(ToolCall(id="c1", name="odd")) == "odd"


def test_tool_spec_builds_a_tool_spec() -> None:
    assert tool_spec("x", "does x", {}) == ToolSpec(name="x", description="does x", parameters={})


def test_object_schema_defaults_to_no_required_fields() -> None:
    assert object_schema({}) == {"type": "object", "properties": {}, "required": []}


def test_file_name_arg_returns_the_file_name() -> None:
    assert file_name_arg({"path": "C:/Docs/report.pdf"}) == "report.pdf"


def test_file_name_arg_has_a_fallback_without_a_path() -> None:
    assert file_name_arg({}) == "a file"


def test_approval_group_ties_the_file_creation_tools_together() -> None:
    assert set(approval_group("create_spreadsheet")) == {"create_document", "create_spreadsheet"}


def test_approval_group_is_just_the_tool_otherwise() -> None:
    assert approval_group("open_app") == ("open_app",)
