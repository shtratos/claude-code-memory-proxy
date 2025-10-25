# Claude Code Memory Proxy

A system that enables Claude Code to use Anthropic's Memory API through a local MCP server with a transparent streaming proxy.

## Architecture

```
Claude Code
    ↓ (uses MCP tool: memory__memory_20250818)
MCP Server (wraps Anthropic's memory tool)
    ↓ (local file operations)
Local filesystem (/memories)

AND in parallel:

Claude Code
    ↓ (API requests)
Proxy (translates tool names)
    ↓ (forwards to upstream)
Upstream API
```

## Components

1. **MCP Memory Server**: Local file-based memory storage
2. **Streaming Proxy**: Bidirectional tool name translation for SSE streams

## Status

Project in initial development.

**Started**: 2025-10-25
**Repository**: github.com/shtratos/claude-code-memory-proxy
