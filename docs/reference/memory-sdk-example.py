"""Minimal example translating the Anthropic memory SDK pattern to a local file backend.
Adapted and condensed from Anthropic documentation for convenience. Not executed
as part of the library; use it as reference only.
"""

from pathlib import Path
from typing import List

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


class LocalFilesystemMemoryTool(BetaAbstractMemoryTool):
    """File-backed memory tool implementation."""

    def __init__(self, base_path: str = "./memory") -> None:
        super().__init__()
        self.memory_root = Path(base_path) / "memories"
        self.memory_root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        if not path.startswith("/memories"):
            raise ValueError("Memory paths must stay under /memories")
        relative = path[len("/memories") :].lstrip("/")
        resolved = self.memory_root / relative
        resolved.resolve().relative_to(self.memory_root.resolve())
        return resolved

    @override
    def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        target = self._resolve(command.path)
        if target.is_dir():
            entries: List[str] = []
            for entry in sorted(target.iterdir()):
                if entry.name.startswith("."):
                    continue
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"- {entry.name}{suffix}")
            return "\n".join(entries) or "(empty directory)"

        if not target.exists():
            raise FileNotFoundError(command.path)

        lines = target.read_text(encoding="utf-8").splitlines()
        if command.view_range:
            start = max(command.view_range[0], 1) - 1
            end = len(lines) if command.view_range[1] == -1 else command.view_range[1]
            lines = lines[start:end]
            start_num = start + 1
        else:
            start_num = 1
        return "\n".join(f"{i + start_num:4d}: {line}" for i, line in enumerate(lines))

    @override
    def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        target = self._resolve(command.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(command.file_text, encoding="utf-8")
        return "created"

    @override
    def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        target = self._resolve(command.path)
        content = target.read_text(encoding="utf-8")
        target.write_text(content.replace(command.old_str, command.new_str), encoding="utf-8")
        return "replaced"

    @override
    def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        target = self._resolve(command.path)
        lines = target.read_text(encoding="utf-8").splitlines()
        index = max(command.insert_line - 1, 0)
        lines.insert(index, command.insert_text)
        target.write_text("\n".join(lines), encoding="utf-8")
        return "inserted"

    @override
    def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        target = self._resolve(command.path)
        if target.is_dir():
            for child in target.iterdir():
                if child.is_dir():
                    delete_cmd = BetaMemoryTool20250818DeleteCommand(path=str(child))
                    self.delete(delete_cmd)  # recursive delete
                else:
                    child.unlink()
            target.rmdir()
        else:
            target.unlink(missing_ok=True)
        return "deleted"

    @override
    def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        source = self._resolve(command.old_path)
        target = self._resolve(command.new_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return "renamed"
