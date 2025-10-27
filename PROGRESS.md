# Progress Log - memory-proxy-v1

**Started**: 2025-10-25T14:30:45Z
**Last Updated**: 2025-10-26T01:10:00Z

---

## 2025-10-26

### 03:15 - Proxy/Memory Tool Contract Alignment Requirements (from manager)
- **Context**: Confirmed that upstream Anthropic API expects the native memory tool contract; our proxy must adapt MCP usage without exposing custom tool specs.
- **Requirements**:
  - Rewrite outbound `tools` entries so `memory__memory_20250818` becomes exactly `{"type": "memory_20250818", "name": "memory"}` (drop MCP-only fields).
  - Ensure `anthropic-beta` header always includes `context-management-2025-06-27`.
  - Convert every outgoing `tool_use` block name to `memory` before forwarding, and convert incoming `memory` tool responses back to the MCP-prefixed name for the client (covers SSE and JSON).
  - Maintain this translation for the full dialogue loop: client tool executions → follow-up requests → subsequent streamed responses.
  - Provide integration evidence: run proxy on :15041 with upstream https://api.anthropic.com, issue a “remember the time when …” flow, capture upstream traffic showing native memory tool usage and client stream showing MCP-prefixed names.
  - Include streaming verification in tests/logs to prove chunk-by-chunk renaming.
- **Action**: Incorporate these explicit requirements into implementation/testing work; update docs/tests accordingly.

### 03:50 - Proxy translation updated to native memory tool contract
- Reworked `proxy.py` to rewrite outgoing MCP memory tool specs into `{"name":"memory","type":"memory_20250818"}` before forwarding, translate `tool_choice`/`tool_use` blocks in both directions, and append the beta header automatically.
- Streaming and JSON response handlers now convert upstream `memory` tool names back to MCP-prefixed equivalents for Claude.
- Added test coverage for tool spec rewriting, tool choice recursion, SSE rewriting, and JSON response normalization (`tests/test_proxy_utils.py`).
- `uv run pytest` now passes (12 tests) confirming the new translation logic.

### 04:05 - Fixed SSE passthrough so rewritten events reach the client
- Found issue where `StreamingResponse` closed the upstream connection before our generator could relay events, resulting in empty client streams (upstream logs still showed tool uses).
- Refactored streaming path to keep the `httpx` stream context open until the async iterator completes, ensuring transformed SSE chunks reach the client (`proxy.py`).
- Verified end-to-end with curl routed through mitmproxy: upstream traffic uses native `memory` tool, client sees MCP-prefixed `memory__memory_20250818` events.

### 04:20 - Added automated Claude CLI memory scenario
- New helper script `scripts/run_claude_memory_scenario.sh` provisions a fresh memories directory, writes a Claude settings/MCP config that targets the proxy and routes all HTTP(S) through mitmproxy, then runs three non-interactive prompts that exercise memory view/store/recall flows.
- Script records the conversation transcript and points to locations for config, logs, and stored memories for inspection.

### 04:35 - Updated proxy to support Claude CLI `mcp__memory__memory_20250818`
- Claude non-interactive runs exposed the actual tool identifier published to the model (`mcp__memory__memory_20250818`), so proxy translation now recognises both the new and legacy `memory__memory_20250818` aliases when rewriting requests/responses.
- Added pytest coverage for the new alias set and reran the automated scenario; curl + Claude runs now show upstream traffic using the native memory tool while Claude receives the MCP-prefixed name it advertises.

### 04:50 - Added global `ccyolo-with-memory` launcher
- Installed project entry points globally via `uv tool install -e .` to expose `memory-server` / `memory-proxy` on PATH.
- Created helper script to generate a transient Claude settings/MCP config that targets the local proxy, routes through mitmproxy, and defaults the memories directory to a user-provided path.
- Script can be invoked from any directory; tested with `--version` to confirm configuration wiring.

### 01:10 - Plan to Align Proxy with Official Memory Tool Contract
- **Goal**: Ensure the proxy converts MCP-style memory tool usage into the exact API format (and back) so official memory interactions work transparently.
- **Tasks**:
  1. **Audit** current behavior to map how MCP tool metadata and `tool_use` blocks are flowing through `proxy.py`.
  2. **Update request translation**:
     - Detect tools named `memory__memory_20250818` and rewrite to `{"type": "memory_20250818", "name": "memory"}` before forwarding upstream.
     - Strip or adapt any MCP-specific fields (`input_schema`) to match Anthropic requirements.
     - Ensure outbound messages no longer inject manual `tool_use` blocks; rely on the model to trigger the tool.
  3. **Update response translation**:
     - When upstream returns `tool_use` events with `{"name": "memory", "type": "memory_20250818"}`, add the MCP prefix (`memory__memory_20250818`) so Claude continues to see the MCP tool name.
     - Confirm SSE and JSON responses both follow this rule.
  4. **Adjust tests**:
     - Extend proxy unit tests to cover the new conversion logic (both directions).
     - Add an integration-style test that simulates an Anthropic response containing `memory` tool usage.
  5. **Validation**:
     - Run the official curl example through the proxy to confirm the upstream logs show `type: memory_20250818` and that the proxy surfaces the tool call as `memory__memory_20250818` on the way back.
     - Capture a mitmproxy log snippet proving the translation occurred.
- **Notes**: This plan replaces the earlier “manual tool call” workaround with the documented workflow. Once complete, the proxy should be indistinguishable from Anthropic’s native handling while still supporting MCP-prefixed tooling on the Claude side.

---

## 2025-10-25

### 14:30 - Workspace Initialized
- Worktree created from shtratos/claude-code-memory-proxy:main
- Branch: chore-cleanup
- Session: memory-proxy-v1
- Ready to work

---

*Maintained by Miku*
