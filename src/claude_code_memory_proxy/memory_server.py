from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Optional

from anthropic.types.beta import BetaMemoryTool20250818Command
from mcp.server.fastmcp import FastMCP
from pydantic import TypeAdapter

from .memory_tool import FileMemoryTool

MEMORY_COMMAND_ADAPTER: TypeAdapter[BetaMemoryTool20250818Command] = TypeAdapter(
    BetaMemoryTool20250818Command
)


def _memory_root_from_env() -> Path:
    memory_dir = os.environ.get("MEMORY_DIR", "./memories")
    root_path = Path(memory_dir)
    if not root_path.is_absolute():
        root_path = Path.cwd() / root_path
    return root_path


def build_memory_tool() -> FileMemoryTool:
    return FileMemoryTool(_memory_root_from_env())


def _build_command_payload(
    command: str,
    *,
    path: str | None = None,
    view_range: Optional[List[int]] = None,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    insert_text: str | None = None,
    old_path: str | None = None,
    new_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"command": command}

    match command:
        case "view":
            if path is None:
                raise ValueError("view command requires path")
            payload["path"] = path
            if view_range is not None:
                if len(view_range) != 2:
                    raise ValueError("view_range must contain exactly two integers")
                payload["view_range"] = view_range
        case "create":
            if path is None or file_text is None:
                raise ValueError("create command requires path and file_text")
            payload["path"] = path
            payload["file_text"] = file_text
        case "str_replace":
            if path is None or old_str is None or new_str is None:
                raise ValueError("str_replace requires path, old_str, and new_str")
            payload["path"] = path
            payload["old_str"] = old_str
            payload["new_str"] = new_str
        case "insert":
            if path is None or insert_line is None or insert_text is None:
                raise ValueError("insert requires path, insert_line, and insert_text")
            payload["path"] = path
            payload["insert_line"] = insert_line
            payload["insert_text"] = insert_text
        case "delete":
            if path is None:
                raise ValueError("delete command requires path")
            payload["path"] = path
        case "rename":
            if old_path is None or new_path is None:
                raise ValueError("rename requires old_path and new_path")
            payload["old_path"] = old_path
            payload["new_path"] = new_path
        case "clear_all_memory":
            # No additional fields required
            pass
        case _:
            raise ValueError(f"Unsupported command: {command}")

    return payload


def create_app() -> FastMCP:
    mcp = FastMCP("memory")
    memory_tool = build_memory_tool()

    @mcp.tool(
        name="memory_20250818",
        description="Persistent memory tool for Claude Code (file-backed storage).",
    )
    def memory_tool_handler(
        command: str,
        path: str | None = None,
        *,
        view_range: Optional[List[int]] = None,
        file_text: str | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
        insert_text: str | None = None,
        old_path: str | None = None,
        new_path: str | None = None,
    ) -> str:
        payload = _build_command_payload(
            command,
            path=path,
            view_range=view_range,
            file_text=file_text,
            old_str=old_str,
            new_str=new_str,
            insert_line=insert_line,
            insert_text=insert_text,
            old_path=old_path,
            new_path=new_path,
        )

        try:
            parsed = MEMORY_COMMAND_ADAPTER.validate_python(payload)
            result = memory_tool.execute(parsed)
            if isinstance(result, (str, bytes)):
                return result.decode() if isinstance(result, bytes) else result
            return json.dumps(result)
        except Exception as exc:  # pragma: no cover - surfaced to Claude
            return f"Error: {exc}"

    return mcp


def main() -> None:
    app = create_app()
    app.run()


if __name__ == "__main__":
    main()
