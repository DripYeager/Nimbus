from __future__ import annotations

from models.chat import ShownCode
from ui.chat.chat_session import step_detail
from ui.chat.code_block import (
    LESS_TEXT,
    MORE_MARK,
    PREVIEW_CHARS,
    PREVIEW_LINES,
    CodeBlock,
    StepDetail,
    output_block,
    preview_of,
    show_all_text,
)
from ui.chat.message_cards import ConfirmCard, ToolStep

LONG = "\n".join(f"print({n})" for n in range(12))


def test_preview_of_keeps_short_text_whole() -> None:
    assert preview_of("ipconfig /all") == "ipconfig /all"


def test_preview_of_cuts_many_lines() -> None:
    preview = preview_of(LONG)

    assert preview.splitlines()[:PREVIEW_LINES] == LONG.splitlines()[:PREVIEW_LINES]
    assert preview.endswith(MORE_MARK)


def test_preview_of_cuts_one_very_long_line() -> None:
    assert len(preview_of("x" * 2000)) <= PREVIEW_CHARS + 4


def test_show_all_text_counts_lines() -> None:
    assert show_all_text(LONG) == "Show all 12 lines"


def test_code_block_toggles_between_preview_and_everything(qapp: object) -> None:
    block = CodeBlock(ShownCode(title="Python", text=LONG))

    block.toggle()

    assert block.is_expanded() and block._text.text() == LONG and block._toggle.text() == LESS_TEXT
    block.toggle()
    assert not block.is_expanded() and block._text.text() == preview_of(LONG)


def test_code_block_short_code_has_nothing_to_open(qapp: object) -> None:
    block = CodeBlock(ShownCode(title="PowerShell", text="ipconfig"))

    block.toggle()

    assert not block.can_expand() and not block.is_expanded() and block._toggle.isHidden()


def test_code_block_copy_puts_everything_on_the_clipboard(qapp: object, mocker) -> None:
    clipboard = mocker.patch("ui.chat.code_block.QGuiApplication.clipboard")
    block = CodeBlock(ShownCode(title="Python", text=LONG))

    block._copy.click()

    clipboard.return_value.setText.assert_called_once_with(LONG)


def test_output_block_says_when_nothing_was_printed(qapp: object) -> None:
    assert output_block("   ")._full == "(nothing printed)"


def test_tool_step_shows_code_then_output_once(qapp: object) -> None:
    step = ToolStep()
    code = ShownCode(title="Python", text="print(6)")

    step.show_detail(StepDetail(code=code))
    step.show_detail(StepDetail(code=code, output="6"))
    step.show_detail(StepDetail(code=code, output="6"))

    assert len(step.findChildren(CodeBlock)) == 2


def test_confirm_card_shows_the_code(qapp: object) -> None:
    card = ConfirmCard("Run Python code", None, False, ShownCode(title="Python", text="print(6)"))

    [block] = card.findChildren(CodeBlock)
    assert block._full == "print(6)"


def test_step_detail_reads_code_and_output() -> None:
    detail = step_detail({"code": {"title": "PowerShell", "text": "ipconfig"}, "output": "IPv4 ..."})

    assert detail == StepDetail(code=ShownCode(title="PowerShell", text="ipconfig"), output="IPv4 ...")
    assert step_detail({"call_id": "a"}) is None
