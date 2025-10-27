# Claude Code Memory Proxy

An experimental weekend project that gives Claude Code (and other MCP clients) persistent memory **today** by combining:

- **`memory-server`** – a Model Context Protocol (MCP) server that implements Anthropic’s `memory_20250818` tool on top of the local filesystem with strict path validation.
- **`memory-proxy`** – a FastAPI streaming proxy that rewrites tool metadata between the MCP format (`mcp__memory__memory_20250818` / `memory__memory_20250818`) and the upstream Anthropic API format (`memory`) while preserving SSE streaming semantics.

> ℹ️ This was built before the official Claude Code memory feature shipped. It may be rendered obsolete quickly, but the translation patterns and agent workflow are still useful.

---

## Features

- File-backed memory storage beneath `/memories`, guarded against path traversal and root deletion.
- Bidirectional tool name translation (supports both `mcp__memory__memory_20250818` and the legacy `memory__memory_20250818` prefixes).
- Streaming-safe SSE rewriting so clients see MCP-prefixed tool names while the upstream API sees native ones.
- Helper scripts for end-to-end verification (curl smoke tests, mitmproxy log inspection, Claude CLI scenario runner).

---

Official documentation:

- Claude Code overview: https://docs.claude.com/en/docs/claude-code/overview
- Anthropic memory tool reference: https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool

Project planning notes: [docs/TASK_PLAN.md](docs/TASK_PLAN.md)
Local references:
- [Memory tool reference](docs/reference/memory-tool-docs.md)
- [Memory SDK example](docs/reference/memory-sdk-example.py)

## Prerequisites

- Python 3.12+
- One of:
  - [`uv`](https://docs.astral.sh/uv/) (recommended)
  - Standard `pip` / virtualenv tooling
- Access to the Anthropic API (`https://api.anthropic.com`)
- Optional:
  - `claude` CLI (for the automated scenario script)
  - [`mitmproxy`](https://mitmproxy.org/) if you want to capture upstream traffic

---

## Installation

Clone the repository and install dependencies with `uv`:

```bash
uv sync
```

Expose the CLI entry points globally (optional but convenient):

```bash
uv tool install -e .
```

This installs:

- `memory-server` – MCP memory server entry point
- `memory-proxy` – streaming proxy entry point

Using `pip` instead:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Quick Start

1. **Start the MCP memory server**

   ```bash
   MEMORY_DIR=./memories uv run memory-server
   ```

   You can inspect it with the MCP Inspector:

   ```bash
   npx @modelcontextprotocol/inspector memory-server
   ```

2. **Start the streaming proxy**

   ```bash
   UPSTREAM_API_URL=https://api.anthropic.com \
   PROXY_PORT=15041 \
   uv run memory-proxy
   ```

   Verify it is healthy:

   ```bash
   curl http://localhost:15041/health
   ```

3. **Forward a request through the proxy** (replace the model if required)

   ```bash
   curl -N http://localhost:15041/v1/messages \
     -H "Content-Type: application/json" \
     -H "anthropic-version: 2023-06-01" \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -d '{
       "model": "'${CLAUDE_MODEL:-claude-sonnet-4-5}'",
       "stream": true,
       "tools": [{"name": "mcp__memory__memory_20250818"}],
       "messages": [{"role": "user", "content": "Check your memory."}]
     }'
   ```

   The proxy removes the MCP prefix before forwarding upstream and adds it back to streamed responses.

---

## Automated Scenario (Claude CLI)

`scripts/run_claude_memory_scenario.sh` drives a three-prompt non-interactive session against the proxy to confirm memory read/write behaviour.

Requirements:

- `claude` CLI installed and configured
- `mitmproxy` certificates available at `~/.mitmproxy`
- (Optional) exported `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` to override defaults

The script:

- Creates an isolated memories directory under `data/`
- Generates a per-run Claude settings/MCP config
- Logs outputs to `data/random-access-memories/<timestamp>/`
- Prints a brief troubleshooting hint if the upstream response reports errors
- To capture traffic with mitmproxy, export `HTTP(S)_PROXY`, `NO_PROXY`, and any certificate bundle variables before running the script.

---

## Helper Scripts

| Script | Description | Requirements |
| --- | --- | --- |
| `scripts/invoke_memory_tool.py` | Sends a minimal Anthropic API request that forces a memory tool call. Useful for debugging translation without a full client. | `requests` (`uv sync --group dev`) |
| `scripts/run_proxy.sh` | Convenience wrapper to launch the proxy with environment variables. | None |

All helper scripts respect `HTTP(S)_PROXY` so they can be routed through mitmproxy when needed.

---

## Testing & Development

- Run unit tests:

  ```bash
  uv run pytest
  ```

- Development dependencies (including `pytest`, `requests`, and `mitmproxy`) can be installed via:

  ```bash
  uv sync --group dev
  ```

- The proxy and helper scripts honour `HTTP_PROXY` / `HTTPS_PROXY` environment variables, so you can instrument upstream calls with mitmproxy or other tooling.
- Continuous integration is not set up yet; run the test suite locally before opening pull requests.

---

## Configuration Reference

| Variable | Default | Description |
| --- | --- | --- |
| `MEMORY_DIR` | `./memories` | Root directory for stored memories |
| `UPSTREAM_API_URL` | `https://api.anthropic.com` | Base URL for the Anthropic API |
| `PROXY_PORT` | `15041` | Port the proxy listens on |
| `ANTHROPIC_API_KEY` | (none) | Passed through to upstream requests as `x-api-key` |
| `ANTHROPIC_BETA` | `context-management-2025-06-27` | Comma-merged into the `anthropic-beta` header (case-insensitive) |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Default model used in helper scripts |

Both tool prefixes (`mcp__memory__memory_20250818` and `memory__memory_20250818`) are accepted by the proxy and rewritten to the upstream-native `{"name": "memory", "type": "memory_20250818"}` format.

The proxy forwards all headers except hop-by-hop headers (e.g., `host`, `content-length`, `connection`). Token and tracing headers set by the client are preserved.

---

## Compatibility & Caveats

- The implementation targets `memory_20250818`. If Anthropic revises the memory tool schema or identifier, update the proxy translation constants accordingly.
- File-backed storage is local to the machine running the MCP server. This project does not provide authentication, quotas, or remote storage.
- Treat this as a reference / experimental implementation. Expect to revisit once the official Claude Code memory feature ships.

---

## Limitations & Notes

- This is a local file-based prototype and does not implement authentication, quotas, or remote storage.
- Built quickly with autonomous agents; expect rough edges and treat as a reference implementation.
- Official Anthropic support for Claude Code memory may supersede this project soon.

---

## Troubleshooting

- **Upstream returns `400`** – double-check `ANTHROPIC_API_KEY`, `ANTHROPIC_BETA`, and model availability. The helper scripts default to safe placeholder values.
- **SSL errors using mitmproxy** – ensure `~/.mitmproxy/combined-ca-bundle.crt` exists and the `claude` CLI trusts it.
- **Tool not invoked** – confirm the client advertises `mcp__memory__memory_20250818` (or `memory__memory__20250818`) and the proxy rewrites it (see helper scripts and the proxy logs).

---

## License

Released under the [MIT License](./LICENSE).

---

## Acknowledgements

- [Anthropic MCP](https://github.com/modelcontextprotocol) for the server framework
- `fastapi`, `httpx`, and `uvicorn` for the proxy stack
- The many agent workflows that helped prototype this over a weekend
- See [ARCHITECTURE.md](./ARCHITECTURE.md) for a high-level component overview.
- See [SECURITY.md](./SECURITY.md) for responsible use guidance.
