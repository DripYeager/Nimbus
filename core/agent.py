"""
The assistant loop: lets the model call tools until it can answer, streaming its words and
each tool step as events. Pauses before any action tool the user hasn't pre-approved, and
resumes once they decide. Owns the loop only — tools, prompts, persistence and the HTTP layer
live elsewhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from config.settings import get_settings
from core.exceptions import ToolsUnsupportedError
from core.logger import get_logger
from llm.provider import LLMProvider
from models.chat import (
    ChatEvent,
    ChatMessage,
    ChatSources,
    ChatToken,
    ConfirmationNeeded,
    ConfirmRequest,
    TextDelta,
    ToolActivity,
    ToolCall,
    ToolResult,
)
from models.schema import SourceRef
from tools.registry import ToolRegistry

logger = get_logger(__name__)

# How much history the model sees; older turns stay saved but stop costing tokens.
CONTEXT_MESSAGES = 30
# A tool result bigger than this is almost always a whole document the model asked for —
# trimming keeps one call from blowing a small local model's context window.
MAX_TOOL_RESULT_CHARS = 12000
DECLINED_MESSAGE = "The user declined this action. Don't retry it unless they ask again."
STEP_LIMIT_MESSAGE = "\n\n_I stopped here after several steps — ask me to continue if you need more._"

FallbackAnswer = Callable[[str], tuple[Iterator[str], list[SourceRef]]]


class Agent:
    """Runs one user turn (or the rest of one, after a confirmation) to completion."""

    def __init__(
        self, provider: LLMProvider, registry: ToolRegistry, system_prompt: Callable[[], str], fallback: FallbackAnswer
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt
        self._fallback = fallback

    def run(self, messages: list[ChatMessage], decision: ConfirmRequest | None = None) -> Iterator[ChatEvent]:
        """Continues the conversation in messages, appending every new assistant and tool
        message to it in place. Ends after the model answers, after it hits the step limit,
        or right after a ConfirmationNeeded event when an action needs the user's go-ahead."""
        sources: list[SourceRef] = []
        awaiting = yield from self._run_pending_calls(messages, decision, sources)
        steps = 0
        while not awaiting and steps < get_settings().max_agent_steps:
            steps += 1
            calls = yield from self._model_turn(messages, sources, is_first=steps == 1 and decision is None)
            if not calls:
                break
            awaiting = yield from self._run_pending_calls(messages, None, sources)
        else:
            if not awaiting:
                # Saved as a real message, so the note is still there when the chat is reopened.
                messages.append(ChatMessage(role="assistant", content=STEP_LIMIT_MESSAGE.strip()))
                yield ChatToken(text=STEP_LIMIT_MESSAGE)
        if sources:
            yield ChatSources(sources=_dedupe(sources))

    def _model_turn(self, messages: list[ChatMessage], sources: list[SourceRef], is_first: bool) -> Iterator[ChatEvent]:
        """Streams one model response, records it, and returns the tool calls it asked for.
        A model without tool support falls back to a plain retrieval answer on the first turn."""
        text, calls = "", []
        try:
            for item in self._provider.stream_chat(
                self._system_prompt(), _model_view(messages), self._registry.specs()
            ):
                if isinstance(item, TextDelta):
                    text += item.text
                    yield ChatToken(text=item.text)
                else:
                    calls.append(item)
        except ToolsUnsupportedError:
            if not is_first or text:
                raise
            logger.info("Model can't use tools, answering from retrieval instead")
            yield from self._fallback_turn(messages, sources)
            return []
        messages.append(ChatMessage(role="assistant", content=text, tool_calls=calls))
        return calls

    def _fallback_turn(self, messages: list[ChatMessage], sources: list[SourceRef]) -> Iterator[ChatEvent]:
        """Answers the latest question from retrieved excerpts, without tools."""
        question = next((m.content for m in reversed(messages) if m.role == "user"), "")
        tokens, found = self._fallback(question)
        sources.extend(found)
        text = ""
        for token in tokens:
            text += token
            yield ChatToken(text=token)
        messages.append(ChatMessage(role="assistant", content=text))

    def _run_pending_calls(
        self, messages: list[ChatMessage], decision: ConfirmRequest | None, sources: list[SourceRef]
    ) -> Iterator[ChatEvent]:
        """Runs every unanswered tool call from the latest assistant message, in order.
        Returns True if it had to stop and ask the user about one."""
        for call in pending_tool_calls(messages):
            if decision is not None and call.id == decision.call_id:
                result = yield from self._decide(call, decision.approved)
            elif self._needs_confirmation(call):
                yield ConfirmationNeeded(
                    call_id=call.id, tool=call.name, description=self._registry.describe_call(call)
                )
                return True
            else:
                result = yield from self._execute(call)
            sources.extend(result.sources)
            messages.append(_tool_message(call, result))
        return False

    def _decide(self, call: ToolCall, approved: bool) -> Iterator[ChatEvent]:
        """Runs an approved call, or records the user's refusal as its result."""
        if approved:
            return (yield from self._execute(call))
        label = self._registry.describe_call(call)
        yield ToolActivity(call_id=call.id, tool=call.name, label=label, status="denied")
        return ToolResult(content=DECLINED_MESSAGE)

    def _execute(self, call: ToolCall) -> Iterator[ChatEvent]:
        """Runs one tool, bracketed by running/done activity events."""
        label = self._registry.describe_call(call)
        yield ToolActivity(call_id=call.id, tool=call.name, label=label, status="running")
        result = self._registry.execute(call)
        yield ToolActivity(call_id=call.id, tool=call.name, label=label, status="failed" if result.is_error else "done")
        return result

    def _needs_confirmation(self, call: ToolCall) -> bool:
        """Action tools ask first, unless the user chose "always allow" for that tool."""
        tool = self._registry.get(call.name)
        if tool is None or not tool.requires_confirmation:
            return False
        return call.name not in get_settings().auto_approved_tools


def pending_tool_calls(messages: list[ChatMessage]) -> list[ToolCall]:
    """Tool calls in the latest assistant message that don't have a result yet."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "assistant":
            answered = {m.tool_call_id for m in messages[index + 1 :] if m.role == "tool"}
            return [c for c in messages[index].tool_calls if c.id not in answered]
    return []


def _model_view(messages: list[ChatMessage]) -> list[ChatMessage]:
    """The recent tail of the conversation, cut at a user message so a tool result is never
    separated from the call that produced it. A long tool run with no user message in the tail
    keeps everything back to the latest user message instead."""
    if len(messages) <= CONTEXT_MESSAGES:
        return messages
    user_indexes = [i for i, m in enumerate(messages) if m.role == "user"]
    tail_start = len(messages) - CONTEXT_MESSAGES
    cut = next((i for i in user_indexes if i >= tail_start), user_indexes[-1] if user_indexes else 0)
    return messages[cut:]


def _tool_message(call: ToolCall, result: ToolResult) -> ChatMessage:
    content = result.content
    if len(content) > MAX_TOOL_RESULT_CHARS:
        content = content[:MAX_TOOL_RESULT_CHARS] + "\n[cut short]"
    return ChatMessage(role="tool", content=content, tool_call_id=call.id, tool_name=call.name)


def _dedupe(sources: list[SourceRef]) -> list[SourceRef]:
    """One entry per file, first mention wins."""
    seen: dict[str, SourceRef] = {}
    for source in sources:
        seen.setdefault(source.file_path.lower(), source)
    return list(seen.values())
