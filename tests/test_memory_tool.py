from __future__ import annotations

from pathlib import Path

import pytest
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)

from claude_code_memory_proxy.memory_tool import FileMemoryTool


@pytest.fixture()
def memory_tool(tmp_path: Path) -> FileMemoryTool:
    memory_root = tmp_path / "memories"
    return FileMemoryTool(memory_root)


def test_create_view_and_modify(memory_tool: FileMemoryTool) -> None:
    create_cmd = BetaMemoryTool20250818CreateCommand(
        command="create",
        path="/memories/notes.txt",
        file_text="hello",
    )
    result = memory_tool.create(create_cmd)
    assert "Created" in result

    view_cmd = BetaMemoryTool20250818ViewCommand(
        command="view",
        path="/memories/notes.txt",
    )
    view_output = memory_tool.view(view_cmd)
    assert "hello" in view_output

    insert_cmd = BetaMemoryTool20250818InsertCommand(
        command="insert",
        path="/memories/notes.txt",
        insert_line=1,
        insert_text="world",
    )
    memory_tool.insert(insert_cmd)

    replace_cmd = BetaMemoryTool20250818StrReplaceCommand(
        command="str_replace",
        path="/memories/notes.txt",
        old_str="world",
        new_str="planet",
    )
    memory_tool.str_replace(replace_cmd)

    updated = memory_tool.view(view_cmd)
    assert "planet" in updated


def test_rename_and_delete(memory_tool: FileMemoryTool) -> None:
    memory_tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/data.txt",
            file_text="data",
        )
    )

    rename_cmd = BetaMemoryTool20250818RenameCommand(
        command="rename",
        old_path="/memories/data.txt",
        new_path="/memories/archive/data.txt",
    )
    memory_tool.rename(rename_cmd)

    delete_cmd = BetaMemoryTool20250818DeleteCommand(
        command="delete",
        path="/memories/archive/data.txt",
    )
    memory_tool.delete(delete_cmd)

    with pytest.raises(FileNotFoundError):
        memory_tool.view(
            BetaMemoryTool20250818ViewCommand(
                command="view",
                path="/memories/archive/data.txt",
            )
        )


def test_rejects_path_traversal(memory_tool: FileMemoryTool) -> None:
    with pytest.raises(ValueError):
        memory_tool.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path="/memories/../../etc/passwd",
                file_text="bad",
            )
        )


def test_str_replace_rejects_empty_old(memory_tool: FileMemoryTool) -> None:
    memory_tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/info.txt",
            file_text="content",
        )
    )

    with pytest.raises(ValueError):
        memory_tool.str_replace(
            BetaMemoryTool20250818StrReplaceCommand(
                command="str_replace",
                path="/memories/info.txt",
                old_str="",
                new_str="new",
            )
        )


def test_rename_root_rejected(memory_tool: FileMemoryTool) -> None:
    with pytest.raises(ValueError):
        memory_tool.rename(
            BetaMemoryTool20250818RenameCommand(
                command="rename",
                old_path="/memories",
                new_path="/memories/archive",
            )
        )
