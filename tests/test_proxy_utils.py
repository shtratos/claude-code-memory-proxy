from __future__ import annotations

import json

import httpx
import anyio
import gzip
import pytest

from claude_code_memory_proxy import proxy


def test_strip_and_add_prefix() -> None:
    assert proxy.strip_mcp_prefix("mcp__memory__memory_20250818") == "memory"
    assert proxy.strip_mcp_prefix("memory__memory_20250818") == "memory"
    assert proxy.strip_mcp_prefix("other_tool") == "other_tool"
    assert proxy.add_mcp_prefix("memory") == "mcp__memory__memory_20250818"
    assert proxy.add_mcp_prefix("memory_20250818") == "mcp__memory__memory_20250818"
    assert proxy.add_mcp_prefix("other_tool") == "other_tool"


def test_transform_tool_specs_and_uses() -> None:
    payload = {
        "tools": [
            {"name": "mcp__memory__memory_20250818", "input_schema": {"type": "object"}},
            {"name": "other"},
        ],
        "tool_choice": {"type": "tool", "name": "mcp__memory__memory_20250818"},
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "mcp__memory__memory_20250818"},
                    {"type": "text", "text": "unchanged"},
                ],
                "tool_result": {"type": "tool_result", "name": "mcp__memory__memory_20250818"},
            }
        ],
        "delta": {"tool_choice": {"type": "tool", "name": "mcp__memory__memory_20250818"}},
    }

    proxy.rewrite_tools_for_upstream(payload["tools"])
    assert payload["tools"][0] == {
        "name": "memory",
        "type": "memory_20250818",
    }

    proxy.transform_tool_choice(payload, proxy.strip_mcp_prefix)
    proxy.transform_tool_uses(payload["messages"], proxy.strip_mcp_prefix)

    assert payload["tool_choice"]["name"] == "memory"
    assert payload["delta"]["tool_choice"]["name"] == "memory"
    assert payload["messages"][0]["content"][0]["name"] == "memory"
    assert payload["messages"][0]["tool_result"]["name"] == "memory"

    proxy.transform_tool_choice(payload, proxy.add_mcp_prefix)
    proxy.transform_tool_uses(payload, proxy.add_mcp_prefix)
    assert payload["tool_choice"]["name"] == "mcp__memory__memory_20250818"
    assert payload["delta"]["tool_choice"]["name"] == "mcp__memory__memory_20250818"
    assert payload["messages"][0]["content"][0]["name"] == "mcp__memory__memory_20250818"
    assert (
        payload["messages"][0]["tool_result"]["name"] == "mcp__memory__memory_20250818"
    )


def test_transform_sse_event() -> None:
    event = (
        "event: content_block_start\n"
        "data: {\"type\":\"content_block_start\",\"content_block\":{\"type\":\"tool_use\",\"name\":\"memory_20250818\"}}\n"
    )
    transformed = proxy.transform_sse_event(event.strip())
    assert "\"name\":\"mcp__memory__memory_20250818\"" in transformed
    assert "\"name\":\"memory_20250818\"" not in transformed


def test_transform_sse_event_rewrites_tool_choice() -> None:
    event = (
        "event: message_delta\n"
        "data: {\"type\":\"message_delta\",\"delta\":{\"tool_choice\":{\"type\":\"tool\",\"name\":\"memory\"}}}\n"
    )
    transformed = proxy.transform_sse_event(event.strip())
    assert "\"name\":\"mcp__memory__memory_20250818\"" in transformed


def test_transform_tool_choice_list() -> None:
    payload = {
        "tool_choice": [
            {"type": "tool", "name": "mcp__memory__memory_20250818"},
            {"type": "tool", "name": "other"},
        ]
    }
    proxy.transform_tool_choice(payload, proxy.strip_mcp_prefix)
    assert payload["tool_choice"][0]["name"] == "memory"
    assert payload["tool_choice"][1]["name"] == "other"

    proxy.transform_tool_choice(payload, proxy.add_mcp_prefix)
    assert payload["tool_choice"][0]["name"] == "mcp__memory__memory_20250818"


def test_ensure_beta_header() -> None:
    headers = {}
    proxy.ensure_beta_header(headers)
    assert headers["anthropic-beta"] == proxy.BETA_HEADER_VALUE

    headers["anthropic-beta"] = f"{proxy.BETA_HEADER_VALUE}, another-feature"
    proxy.ensure_beta_header(headers)
    assert proxy.BETA_HEADER_VALUE in headers["anthropic-beta"]


def test_ensure_beta_header_case_insensitive() -> None:
    headers = {"Anthropic-Beta": "foo"}
    proxy.ensure_beta_header(headers)
    assert "Anthropic-Beta" not in headers
    assert proxy.BETA_HEADER_VALUE in headers["anthropic-beta"]
    assert "foo" in headers["anthropic-beta"]


def test_read_json_response_strips_content_encoding() -> None:
    payload = {"content": [{"type": "tool_use", "name": "memory_20250818"}]}
    compressed = gzip.compress(json.dumps(payload).encode("utf-8"))
    response = httpx.Response(
        status_code=200,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
        content=compressed,
        request=httpx.Request("POST", "http://upstream/v1/messages"),
    )

    json_response = anyio.run(proxy.read_json_response, response)
    assert json_response.status_code == 200
    assert json_response.body
    assert "content-encoding" not in {k.lower(): v for k, v in json_response.headers.items()}
    updated_payload = json.loads(json_response.body)
    assert updated_payload["content"][0]["name"] == "mcp__memory__memory_20250818"
