from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Sequence

from anthropic.lib.tools import BetaAbstractMemoryTool
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from typing_extensions import override


class FileMemoryTool(BetaAbstractMemoryTool):
    """File-backed implementation of Anthropic's memory tool.

    Conventions:
    - Paths must live under `/memories`.
    - `view` line ranges are 1-based; `end=-1` includes the remainder of the file.
    - `insert` uses 0-based indices to match Python list semantics.
    """

    def __init__(self, memory_dir: Path) -> None:
        super().__init__()
        self.memory_root = memory_dir.resolve()
        self.memory_root.mkdir(parents=True, exist_ok=True)

    def _validate_path(self, path: str) -> Path:
        """Ensure memory paths stay within /memories."""
        if not path.startswith("/memories"):
            raise ValueError(f"Path must start with /memories, got {path!r}")

        relative = path[len("/memories") :].lstrip("/")
        full_path = self.memory_root / relative

        try:
            full_path.resolve().relative_to(self.memory_root)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Path {path!r} would escape /memories") from exc

        return full_path

    @override
    def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        full_path = self._validate_path(command.path)

        if full_path.is_dir():
            entries: List[str] = []
            for entry in sorted(full_path.iterdir(), key=lambda p: p.name.lower()):
                if entry.name.startswith("."):
                    continue
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"- {entry.name}{suffix}")
            listing = "\n".join(entries) if entries else "(empty directory)"
            return f"Directory: {command.path}\n{listing}"

        if full_path.is_file():
            text = full_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            view_range = command.view_range

            if view_range:
                start = max(view_range[0], 1) - 1
                end = len(lines) if view_range[1] == -1 else min(view_range[1], len(lines))
                subset = lines[start:end]
                start_number = start + 1
            else:
                subset = lines
                start_number = 1

            numbered = (f"{idx + start_number:4d}: {line}" for idx, line in enumerate(subset))
            return "\n".join(numbered)

        raise FileNotFoundError(f"Path not found: {command.path}")

    @override
    def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        full_path = self._validate_path(command.path)
        if full_path.exists():
            raise FileExistsError(f"File already exists: {command.path}")

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(command.file_text, encoding="utf-8")
        return f"Created {command.path}"

    @override
    def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        full_path = self._validate_path(command.path)
        if not full_path.is_file():
            raise FileNotFoundError(f"File not found: {command.path}")

        if command.old_str == "":
            raise ValueError("old_str cannot be empty")

        content = full_path.read_text(encoding="utf-8")

        occurrences = content.count(command.old_str)
        if occurrences == 0:
            raise ValueError(f"Text not found in {command.path}")
        if occurrences > 1:
            raise ValueError(
                f"Text appears {occurrences} times in {command.path}. Must be unique."
            )

        updated = content.replace(command.old_str, command.new_str, 1)
        full_path.write_text(updated, encoding="utf-8")
        return f"Updated {command.path}"

    @override
    def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        full_path = self._validate_path(command.path)
        if not full_path.is_file():
            raise FileNotFoundError(f"File not found: {command.path}")

        lines = full_path.read_text(encoding="utf-8").splitlines()
        insert_line = command.insert_line
        if insert_line < 0 or insert_line > len(lines):
            raise ValueError(f"Invalid insert_line {insert_line}. Expected 0..{len(lines)}")

        insert_text = command.insert_text.rstrip("\n")
        lines.insert(insert_line, insert_text)
        full_path.write_text(_join_lines(lines), encoding="utf-8")
        return f"Inserted text at line {insert_line} in {command.path}"

    @override
    def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        full_path = self._validate_path(command.path)
        if command.path == "/memories":
            raise ValueError("Cannot delete /memories directory")

        if full_path.is_file():
            full_path.unlink()
            return f"Deleted file {command.path}"

        if full_path.is_dir():
            shutil.rmtree(full_path)
            return f"Deleted directory {command.path}"

        raise FileNotFoundError(f"Path not found: {command.path}")

    @override
    def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        source = self._validate_path(command.old_path)
        target = self._validate_path(command.new_path)

        if command.old_path == "/memories":
            raise ValueError("Cannot rename /memories directory")

        if not source.exists():
            raise FileNotFoundError(f"Source path not found: {command.old_path}")
        if target.exists():
            raise FileExistsError(f"Destination already exists: {command.new_path}")

        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return f"Renamed {command.old_path} to {command.new_path}"

    @override
    def clear_all_memory(self) -> str:
        if self.memory_root.exists():
            shutil.rmtree(self.memory_root)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        return "Cleared all memory"


def _join_lines(lines: Sequence[str]) -> str:
    """Join lines ensuring trailing newline if file is non-empty."""
    text = "\n".join(lines)
    if lines:
        return text + "\n"
    return text
