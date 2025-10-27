# Architecture

This project combines two cooperating components to provide persistent memory for MCP-compatible clients such as Claude Code.

```
MCP Client (Claude Code)
 ├─ tool calls: mcp__memory__memory_20250818
 │                 │
 │                 ▼
 │        memory-server (FastMCP + FileMemoryTool)
 │                 │
 │           ./memories/ tree
 │
 └─ HTTP API calls: /v1/messages
                   │
                   ▼
          memory-proxy (FastAPI + httpx)
                   │
                   ▼
        Anthropic API (https://api.anthropic.com)
```

## Request Flow

1. The MCP client advertises the memory tool as `mcp__memory__memory_20250818` (legacy clients may use `memory__memory__20250818`).
2. The proxy receives `/v1/messages` requests, rewrites the tool list and any embedded `tool_use` blocks so the upstream sees `{"name": "memory", "type": "memory_20250818"}`.
3. The proxy ensures the required beta header `context-management-2025-06-27` is present (or the value provided via `ANTHROPIC_BETA`) and forwards the request with hop-by-hop headers stripped.
4. The upstream issues tool calls; streamed SSE events are rewritten on the fly so the client sees MCP-prefixed names again.

## Tool Translation Rules

| Direction | Input | Output |
| --- | --- | --- |
| Client → Proxy | `mcp__memory__memory_20250818` or `memory__memory__memory_20250818` | `{"name": "memory", "type": "memory_20250818"}` |
| Proxy → Client | `{"name": "memory", "type": "memory_20250818"}` | `mcp__memory__memory_20250818` |

Non-memory tool names are passed through unchanged.

## Streaming Handling

- Responses from the upstream API arrive as Server-Sent Events (SSE).
- The proxy buffers events until `\n\n`, deserialises the JSON payload, rewrites any tool names, and re-emits the SSE event to the client.
- JSON responses (non-streaming) go through the same rewrite logic.

## Memory Semantics

The MCP server mounts a file-backed store rooted at `MEMORY_DIR` (default `./memories`):

- Path validation uses `Path.resolve()` and `relative_to` to prevent traversal outside the memory root.
- `/memories` acts as the top-level directory; attempts to delete or rename it are rejected.
- `view` supports range slicing with `view_range=[start, end]` (1-based start, end exclusive; `-1` includes the remainder of the file).
- `insert` uses 0-based indices to align with Python list semantics.
- Hidden files (starting with `.`) are suppressed when listing directories.

## Headers & Configuration

- Required request headers: `anthropic-version`, `x-api-key`, and `anthropic-beta`.
- The proxy enforces the beta header, merging any values case-insensitively and allowing override via `ANTHROPIC_BETA`.
- Environment knobs:
  - `MEMORY_DIR` – location of stored memories
  - `UPSTREAM_API_URL` – upstream endpoint (default `https://api.anthropic.com`)
  - `PROXY_PORT` – listening port (default `15041`)
  - `ANTHROPIC_API_KEY` – passed through as `x-api-key`
  - `ANTHROPIC_BETA` – optional override for the beta header value

## Logging

`memory-proxy` logs a single INFO line per request summarising stream usage and tool names, plus INFO lines for upstream response status. Adjust logging configuration in your hosting environment if you need more detail.
