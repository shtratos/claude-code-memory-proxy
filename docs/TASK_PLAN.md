# Build Claude Code Memory Proxy System

This plan captures the original goals and milestones for creating a Claude Code memory solution that combines an MCP memory server with a streaming proxy.

---

## Project Goal

Enable Claude Code (and other MCP clients) to maintain persistent memory across sessions by:
1. Implementing an MCP memory server that stores data locally.
2. Building a streaming proxy that translates tool names between the MCP format and the Anthropic API format without breaking SSE streaming.

Outcome: Claude Code instances can remember context across sessions until the native feature ships.

---

## Definition of Done

- [ ] MCP memory server implemented and installable via `uv tool install -e .`
- [ ] Streaming proxy rewrites tool names in both directions.
- [ ] Integration tests cover create/read/update flows with Claude Code.
- [ ] Memory persists between separate Claude Code sessions.
- [ ] External review (oracle-codex) completed and feedback addressed.
- [ ] README documents setup, usage, and limitations.

---

## Key References

- Claude Code overview: https://docs.claude.com/en/docs/claude-code/overview
- Anthropic memory tool documentation: https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool
- `reference-docs/memory-tool-docs.md` (Anthropic memory tool spec, included in the workspace)
- `reference-docs/memory-sdk-example.py` (SDK pattern for implementing memory commands)

---

## Technical Notes

- Package manager: [`uv`](https://docs.astral.sh/uv/) (use `uv add`, `uv run`, `uv tool install`)
- Frameworks: `fastmcp` for the MCP server, `fastapi` + `uvicorn` + `httpx` for the proxy
- Anthropic SDK: `anthropic` (provides `BetaAbstractMemoryTool` base class)
- Upstream API: `https://api.anthropic.com` (supply your own API key and beta token)
- Memory storage: configurable via `MEMORY_DIR` (defaults to `./memories`)
- Beta header: `context-management-2025-06-27` (configurable via `ANTHROPIC_BETA`)
- Tool names: MCP advertises `mcp__memory__memory_20250818`; the upstream expects `{ "name": "memory", "type": "memory_20250818" }`

---

## Implementation Phases

### Phase 1 – Project Setup
- Initialize the project with `uv init` (library mode).
- Add dependencies: `anthropic`, `fastmcp`, `fastapi`, `httpx`, `uvicorn`.

### Phase 2 – MCP Memory Server
- Create `FileMemoryTool` implementing commands: `view`, `create`, `str_replace`, `insert`, `delete`, `rename`, `clear_all_memory`.
- Validate all paths remain under `/memories` (use `Path.resolve()` + `relative_to`).
- Wire the tool into an MCP server (`FastMCP`) and expose via `uv run memory-server`.
- Add tests covering filesystem operations and path validation.

### Phase 3 – Streaming Proxy
- Implement `FastAPI` app with `/health` and `/v1/messages` endpoints.
- Translate tool names on the way in (MCP → API) and out (API → MCP).
- Handle SSE streaming by buffering events and rewriting tool names in JSON payloads.
- Preserve client headers (except hop-by-hop ones) and ensure the beta header is set.
- Support configuration via environment variables.

### Phase 4 – Integration Testing
- Verify end-to-end flows using Claude Code or the helper scripts:
  - Create a memory.
  - Read the memory in the same session.
  - Confirm persistence across sessions.
  - Update an existing memory.
- Optionally capture traffic with mitmproxy by setting `HTTP(S)_PROXY` manually.

### Phase 5 – Documentation & Review
- Update `README.md` with setup, usage, troubleshooting, and limitations.
- Capture review feedback (oracle-codex or peer review) and implement fixes.
- Ensure tests pass (`uv run pytest`).

---

## Tips for Success

1. Read the memory tool spec and SDK example before coding.
2. Test incrementally (MCP server first, then proxy, then integration path).
3. Keep path validation strict to avoid security issues.
4. Buffer SSE events until `\n\n` before rewriting JSON data.
5. When debugging, use helper scripts and structured logging rather than modifying production code.
6. Run Claude Code in non-interactive mode during automated tests for predictable behaviour.

---

## Troubleshooting Checklist

- Proxy returns 400: verify API key, beta header, and model availability.
- Tool results not forwarded: ensure the client advertises `mcp__memory__memory_20250818` and confirm translation in logs.
- SSE stream truncated: check buffering logic and ensure upstream connection remains open until all events are emitted.
- File permissions issues: confirm the process can write to `MEMORY_DIR` and that tests clean up temporary directories.

---

## Final Review Checklist

- [ ] MCP server passes unit tests.
- [ ] Proxy passes unit tests for translation logic and SSE rewriting.
- [ ] Integration scenario (`scripts/run_claude_memory_scenario.sh`) completes successfully.
- [ ] README, ARCHITECTURE, and SECURITY docs are up to date.
- [ ] No secrets, personal paths, or internal references remain in the repo.
- [ ] Branch reviewed and ready for public release.

Good luck and happy building!
