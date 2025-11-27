from __future__ import annotations

import json
import os
import tempfile

import httpx
import anyio
import gzip
import pytest
from fastapi import HTTPException

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


# --- System Prompt Patching Tests ---


@pytest.fixture(autouse=True)
def reset_patches_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the system prompt patches cache before each test."""
    monkeypatch.setattr(proxy, "_system_prompt_patches_cache", None)


def test_transform_system_prompt_optional_patch_applied() -> None:
    """Test that optional patches are applied successfully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "old text", "replace": "new text", "required": False}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "This has old text here."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        assert payload["system"][0]["text"] == "This has new text here."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_required_patch_applied() -> None:
    """Test that required patches are applied successfully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "must exist", "replace": "was replaced", "required": True}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "This must exist in the prompt."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        assert payload["system"][0]["text"] == "This was replaced in the prompt."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_required_patch_fails() -> None:
    """Test that a required patch raises HTTPException when not found."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "text that does not exist", "replace": "ignored", "required": True}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "Some other content."}
            ]
        }
        
        with pytest.raises(HTTPException) as excinfo:
            proxy.transform_system_prompt(payload)
        
        assert excinfo.value.status_code == 500
        assert "Required system prompt patch failed" in excinfo.value.detail
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_missing_patch_file() -> None:
    """Test that missing patch file is handled gracefully (no-op)."""
    os.environ["SYSTEM_PROMPT_PATCHES"] = "/nonexistent/path/patches.json"
    try:
        payload = {
            "system": [
                {"type": "text", "text": "Original text."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        # Should not raise and should not modify payload
        assert payload["system"][0]["text"] == "Original text."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)


def test_transform_system_prompt_malformed_patch_file() -> None:
    """Test that malformed JSON patch file is handled gracefully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ invalid json }")
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "Original text."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        # Should not raise and should not modify payload
        assert payload["system"][0]["text"] == "Original text."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_empty_patches_list() -> None:
    """Test that empty patches list results in no-op."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"replacements": []}, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "Original text."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        assert payload["system"][0]["text"] == "Original text."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_no_env_var() -> None:
    """Test that missing env var results in no-op."""
    # Ensure env var is not set
    os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
    
    payload = {
        "system": [
            {"type": "text", "text": "Original text."}
        ]
    }
    proxy.transform_system_prompt(payload)
    
    assert payload["system"][0]["text"] == "Original text."


def test_transform_system_prompt_non_list_system() -> None:
    """Test that non-list system prompt is skipped gracefully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "old", "replace": "new", "required": False}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        
        # String system prompt (not a list)
        payload = {"system": "This is old text."}
        proxy.transform_system_prompt(payload)
        
        # Should not modify string system prompt
        assert payload["system"] == "This is old text."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_no_system_key() -> None:
    """Test that missing system key is handled gracefully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "old", "replace": "new", "required": False}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        
        # No system key at all
        payload_no_system: dict = {"messages": []}
        proxy.transform_system_prompt(payload_no_system)
        
        # Should not raise and should not add system key
        assert "system" not in payload_no_system
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_multiple_blocks() -> None:
    """Test patching across multiple text blocks."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "find this", "replace": "found it", "required": False}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "Block 1 with find this content."},
                {"type": "image", "data": "ignored"},
                {"type": "text", "text": "Block 2 also has find this."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        assert payload["system"][0]["text"] == "Block 1 with found it content."
        assert payload["system"][1] == {"type": "image", "data": "ignored"}
        assert payload["system"][2]["text"] == "Block 2 also has found it."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)


def test_transform_system_prompt_empty_find_string() -> None:
    """Test that patches with empty find string are skipped."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "replacements": [
                {"find": "", "replace": "ignored", "required": False},
                {"find": "real match", "replace": "real replacement", "required": False}
            ]
        }, f)
        config_path = f.name
    
    try:
        os.environ["SYSTEM_PROMPT_PATCHES"] = config_path
        payload = {
            "system": [
                {"type": "text", "text": "Text with real match here."}
            ]
        }
        proxy.transform_system_prompt(payload)
        
        # Only second patch should be applied
        assert payload["system"][0]["text"] == "Text with real replacement here."
    finally:
        os.environ.pop("SYSTEM_PROMPT_PATCHES", None)
        os.unlink(config_path)
