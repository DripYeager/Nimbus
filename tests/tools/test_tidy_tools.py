from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import ToolError
from core.file_tidy import FileTidier
from tools.registry import ToolRegistry
from tools.tidy_tools import TidyToolbox


@pytest.fixture
def share(tmp_path: Path) -> Path:
    folder = tmp_path / "share"
    folder.mkdir()
    (folder / "notes.txt").write_text("hi", encoding="utf-8")
    return folder


def _toolbox(tmp_path: Path, share: Path, everywhere: bool = False) -> TidyToolbox:
    def guard(path: Path) -> bool:
        return everywhere or share.resolve() in path.resolve().parents

    return TidyToolbox(FileTidier(tmp_path / "changes.jsonl"), guard, lambda: [share])


@pytest.fixture
def toolbox(tmp_path: Path, share: Path) -> TidyToolbox:
    return _toolbox(tmp_path, share)


def test_register_every_tool_asks_and_never_always(toolbox: TidyToolbox) -> None:
    registry = ToolRegistry()
    toolbox.register(registry)

    for name in ("move_file", "rename_file", "undo_file_change"):
        assert registry.get(name).needs_confirmation({})
        assert not registry.can_always_allow(name)


def test_register_refused_move_skips_the_card(toolbox: TidyToolbox, share: Path, tmp_path: Path) -> None:
    registry = ToolRegistry()
    toolbox.register(registry)
    move = registry.get("move_file")

    assert move.needs_confirmation({"path": str(share / "notes.txt"), "to_folder": str(share / "A")})
    assert not move.needs_confirmation({"path": str(share / "notes.txt"), "to_folder": str(tmp_path)})
    assert not registry.get("rename_file").needs_confirmation({"path": str(tmp_path / "x"), "new_name": "y"})


def test_register_odd_arguments_still_ask(toolbox: TidyToolbox) -> None:
    registry = ToolRegistry()
    toolbox.register(registry)

    assert registry.get("move_file").needs_confirmation({})


def test_move_inside_share(toolbox: TidyToolbox, share: Path) -> None:
    result = toolbox.move({"path": str(share / "notes.txt"), "to_folder": str(share / "Text")})

    assert (share / "Text" / "notes.txt").exists()
    assert result.content.startswith("Moved")


def test_move_out_of_share_is_refused(toolbox: TidyToolbox, share: Path, tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="isn't inside"):
        toolbox.move({"path": str(share / "notes.txt"), "to_folder": str(tmp_path / "elsewhere")})

    assert (share / "notes.txt").exists()


def test_move_from_outside_share_is_refused(toolbox: TidyToolbox, share: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(ToolError, match="outside"):
        toolbox.move({"path": str(outside), "to_folder": str(share)})


def test_rename_of_shared_folder_itself_is_refused(share: Path, tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="shared folders itself"):
        _toolbox(tmp_path, share, everywhere=True).rename({"path": str(share), "new_name": "other"})


def test_undo_puts_back_and_describe_names_it(toolbox: TidyToolbox, share: Path) -> None:
    toolbox.rename({"path": str(share / "notes.txt"), "new_name": "ideas"})
    args = {"path": str(share / "ideas.txt")}

    assert toolbox.describe_undo(args) == f"Put {share / 'ideas.txt'} back at {share / 'notes.txt'}"
    toolbox.undo(args)

    assert (share / "notes.txt").exists()


def test_undo_refuses_when_a_newer_change_happened_since_the_card(toolbox: TidyToolbox, share: Path) -> None:
    (share / "other.txt").write_text("x", encoding="utf-8")
    toolbox.rename({"path": str(share / "notes.txt"), "new_name": "ideas"})
    stale_card = {"path": str(share / "ideas.txt")}
    toolbox.rename({"path": str(share / "other.txt"), "new_name": "newer"})

    with pytest.raises(ToolError, match="most recent change"):
        toolbox.undo(stale_card)

    assert (share / "newer.txt").exists() and (share / "ideas.txt").exists()


def test_describe_undo_without_a_matching_change(toolbox: TidyToolbox, share: Path) -> None:
    toolbox.rename({"path": str(share / "notes.txt"), "new_name": "ideas"})

    assert toolbox.describe_undo({"path": str(share / "x.txt")}) == f"Undo the last change to {share / 'x.txt'}"


def test_undo_without_a_path_puts_back_the_newest_change(toolbox: TidyToolbox, share: Path) -> None:
    toolbox.rename({"path": str(share / "notes.txt"), "new_name": "ideas"})

    assert toolbox.describe_undo({}) == f"Put {share / 'ideas.txt'} back at {share / 'notes.txt'}"
    toolbox.undo({})

    assert (share / "notes.txt").exists()


def test_describe_undo_with_nothing_to_undo(toolbox: TidyToolbox) -> None:
    assert "there isn't one" in toolbox.describe_undo({})
