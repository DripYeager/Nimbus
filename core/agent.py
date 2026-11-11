"""
The assistant loop: lets the model call tools until it can answer, streaming its words and
each tool step as events. Pauses before any action tool the user hasn't pre-approved, and
resumes once they decide. Owns the loop only; tools, prompts, persistence and the HTTP layer
live elsewhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from config.settings import get_settings
from core.attachment_format import has_attachment, split_attachments
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
    ToolSpec,
)
from models.schema import SourceRef
from tools.registry import ToolRegistry

logger = get_logger(__name__)

# How much history the model sees; older turns stay saved but stop costing tokens.
CONTEXT_MESSAGES = 30
# A tool result bigger than this is almost always a whole document the model asked for,
# trimming keeps one call from blowing a small local model's context window.
MAX_TOOL_RESULT_CHARS = 12000
ATTACHMENT_TOOLS = frozenset({"create_document", "create_spreadsheet"})
EMPTY_ANSWER_MESSAGE = (
    "The model finished without writing an answer. Try asking again, or pick a larger model in Settings."
)
DECLINED_MESSAGE = "The user declined this action. Don't retry it unless they ask again."
STEP_LIMIT_MESSAGE = "\n\n_I stopped here after several steps. Ask me to continue if you need more._"

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
        sources = SourceTracker()
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
        if sources.final():
            yield ChatSources(sources=sources.final())

    def _model_turn(self, messages: list[ChatMessage], sources: SourceTracker, is_first: bool) -> Iterator[ChatEvent]:
        """Streams one model response, records it, and returns the tool calls it asked for.
        A model without tool support falls back to a plain retrieval answer on the first turn."""
        text, calls = "", []
        try:
            for item in self._provider.stream_chat(
                self._system_prompt(), _model_view(messages), self._tools_for(messages)
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
        if not text and not calls:
            # Seen with small local models after reading a long file; a blank reply looks broken.
            text = EMPTY_ANSWER_MESSAGE
            yield ChatToken(text=text)
        messages.append(ChatMessage(role="assistant", content=text, tool_calls=calls))
        return calls

    def _tools_for(self, messages: list[ChatMessage]) -> list[ToolSpec]:
        """Every tool, except when the newest question came with an attachment: the answer is
        in what the user handed over, and small local models otherwise go off searching files
        for it instead of reading it. Making a file from it ("put this table in Excel") still
        works, so the create tools stay."""
        specs = self._registry.specs()
        latest = next((m for m in reversed(messages) if m.role == "user"), None)
        if latest is not None and has_attachment(latest.content):
            return [spec for spec in specs if spec.name in ATTACHMENT_TOOLS]
        return specs

    def _fallback_turn(self, messages: list[ChatMessage], sources: SourceTracker) -> Iterator[ChatEvent]:
        """Answers the latest question from retrieved excerpts, without tools."""
        question = next(m.content for m in reversed(messages) if m.role == "user")
        tokens, found = self._fallback(question)
        sources.add(found)
        text = ""
        for token in tokens:
            text += token
            yield ChatToken(text=token)
        messages.append(ChatMessage(role="assistant", content=text))

    def _run_pending_calls(
        self, messages: list[ChatMessage], decision: ConfirmRequest | None, sources: SourceTracker
    ) -> Iterator[ChatEvent]:
        """Runs every unanswered tool call from the latest assistant message, in order.
        Returns True if it had to stop and ask the user about one."""
        for call in pending_tool_calls(messages):
            if decision is not None and call.id == decision.call_id:
                result = yield from self._decide(call, decision.approved)
            elif self._needs_confirmation(call, messages):
                yield ConfirmationNeeded(
                    call_id=call.id,
                    tool=call.name,
                    description=self._registry.describe_call(call),
                    can_always_allow=self._registry.can_always_allow(call.name),
                )
                return True
            else:
                result = yield from self._execute(call)
            sources.add(result.sources, listing=result.listing)
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

    def _needs_confirmation(self, call: ToolCall, messages: list[ChatMessage]) -> bool:
        """Action tools ask first, unless the user chose "always allow" for that tool (which
        tools that must always ask ignore, even if a setting says otherwise)."""
        tool = self._registry.get(call.name)
        if tool is None or not tool.needs_confirmation(call.arguments, latest_user_text(messages)):
            return False
        if not tool.always_allowable:
            return True
        return call.name not in get_settings().auto_approved_tools

    def can_always_allow(self, tool_name: str) -> bool:
        return self._registry.can_always_allow(tool_name)


def latest_user_text(messages: list[ChatMessage]) -> str:
    """What the user typed in their newest message, without any attached file's text."""
    latest = next((m for m in reversed(messages) if m.role == "user"), None)
    return split_attachments(latest.content)[0] if latest is not None else ""


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


class SourceTracker:
    """The files a turn used, for the source cards. Files that were read or searched win;
    files that were only listed along the way (every PDF in Downloads, say) are shown only
    when nothing was read, so the cards point at what the answer actually came from."""

    def __init__(self) -> None:
        self._used: list[SourceRef] = []
        self._listed: list[SourceRef] = []

    def add(self, refs: list[SourceRef], listing: bool = False) -> None:
        (self._listed if listing else self._used).extend(refs)

    def final(self) -> list[SourceRef]:
        return _dedupe(self._used or self._listed)


def _dedupe(sources: list[SourceRef]) -> list[SourceRef]:
    """One entry per file, first mention wins."""
    seen: dict[str, SourceRef] = {}
    for source in sources:
        seen.setdefault(source.file_path.lower(), source)
    return list(seen.values())
