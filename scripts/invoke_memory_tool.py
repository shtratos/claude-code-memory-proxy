#!/usr/bin/env python3
"""
Send a minimal Anthropic API request that forces a memory tool call.

Usage:
    uv run scripts/invoke_memory_tool.py

This script respects the standard proxy environment variables so it will route
through the memory proxy if HTTP(S)_PROXY is set (as in ~/.claude/settings.json).

Notes:
- Provide any required authentication headers through environment variables (e.g., `ANTHROPIC_API_KEY`).
- Override the model via `CLAUDE_MODEL`; defaults to `claude-sonnet-4-5`.
- The upstream may return a non-success status if the beta feature is unavailable; the goal here is to inspect tool translation behaviour.
"""

from __future__ import annotations

import os
import requests


def main() -> int:
    url = os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:15041").rstrip("/") + "/v1/messages"
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

    payload = {
        "model": model,
        "max_tokens": 10,
        "tools": [
            {
                "name": "mcp__memory__memory_20250818",
                "type": "custom",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "path": {"type": "string"}
                    },
                    "required": ["command", "path"]
                }
            }
        ],
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_demo",
                        "name": "mcp__memory__memory_20250818",
                        "input": {"command": "view", "path": "/memories/demo.md"}
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_demo",
                        "content": ""
                    }
                ]
            }
        ]
    }

    headers = {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key

    print(f"POST {url}")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    print("Status:", response.status_code)
    print("Body:", response.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
