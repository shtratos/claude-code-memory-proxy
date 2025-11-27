from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Callable, Dict, List, MutableMapping

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

MCP_SERVER_PREFIX = "mcp__"
MCP_SERVER_NAME = "memory"
MCP_TOOL_PREFIXES = (
    f"{MCP_SERVER_PREFIX}{MCP_SERVER_NAME}__",
    "memory__",
)
MCP_MEMORY_TOOL_NAME = f"{MCP_TOOL_PREFIXES[0]}memory_20250818"
LEGACY_MCP_MEMORY_TOOL_NAME = "memory__memory_20250818"
API_MEMORY_TOOL_TYPE = "memory_20250818"
API_MEMORY_TOOL_NAME = "memory"
BETA_HEADER_VALUE = os.environ.get("ANTHROPIC_BETA", "context-management-2025-06-27")

logger = logging.getLogger(__name__)


def strip_mcp_prefix(tool_name: str) -> str:
    """Convert an MCP-prefixed tool name to the upstream API format."""
    if tool_name in (MCP_MEMORY_TOOL_NAME, LEGACY_MCP_MEMORY_TOOL_NAME):
        return API_MEMORY_TOOL_NAME
    for prefix in MCP_TOOL_PREFIXES:
        if tool_name.startswith(prefix):
            suffix = tool_name[len(prefix) :]
            if suffix == API_MEMORY_TOOL_TYPE:
                return API_MEMORY_TOOL_NAME
            return suffix
    return tool_name


def add_mcp_prefix(tool_name: str) -> str:
    """Convert an upstream tool name back to the MCP-prefixed form."""
    if tool_name in (API_MEMORY_TOOL_NAME, API_MEMORY_TOOL_TYPE):
        return MCP_MEMORY_TOOL_NAME
    return tool_name


def get_upstream_url() -> str:
    return os.environ.get("UPSTREAM_API_URL", "https://api.anthropic.com").rstrip("/")


def ensure_beta_header(headers: Dict[str, str]) -> None:
    """Ensure the Anthropic beta header is present exactly once (case-insensitive)."""
    key_lower = "anthropic-beta"
    existing_key = None
    for candidate in list(headers.keys()):
        if candidate.lower() == key_lower:
            existing_key = candidate
            break

    if existing_key is not None:
        current = headers.pop(existing_key)
        values = {part.strip() for part in current.split(",") if part.strip()}
    else:
        values = set()

    if BETA_HEADER_VALUE not in values:
        values.add(BETA_HEADER_VALUE)

    headers["anthropic-beta"] = ", ".join(sorted(values))


def rewrite_tools_for_upstream(tools: List[Any]) -> None:
    memory_aliases = {MCP_MEMORY_TOOL_NAME, LEGACY_MCP_MEMORY_TOOL_NAME}
    for index, tool in enumerate(tools):
        if not isinstance(tool, MutableMapping):
            continue
        detected_name: str | None = None
        for key in ("name", "tool_name"):
            value = tool.get(key)
            if isinstance(value, str):
                detected_name = value
                break
        if detected_name in memory_aliases:
            tools[index] = {"name": API_MEMORY_TOOL_NAME, "type": API_MEMORY_TOOL_TYPE}
            continue
        for key in ("name", "tool_name"):
            value = tool.get(key)
            if isinstance(value, str):
                tool[key] = strip_mcp_prefix(value)


def transform_tool_choice(payload: MutableMapping[str, Any], transformer: Callable[[str], str]) -> None:
    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, MutableMapping):
        name = tool_choice.get("name")
        if isinstance(name, str):
            tool_choice["name"] = transformer(name)
    elif isinstance(tool_choice, list):
        for choice in tool_choice:
            if isinstance(choice, MutableMapping):
                name = choice.get("name")
                if isinstance(name, str):
                    choice["name"] = transformer(name)

    for value in payload.values():
        if isinstance(value, MutableMapping):
            transform_tool_choice(value, transformer)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, MutableMapping):
                    transform_tool_choice(item, transformer)


def transform_tool_uses(payload: Any, transformer: Callable[[str], str]) -> None:
    if isinstance(payload, dict):
        t = payload.get("type")
        if t in ("tool_use", "tool_result") and isinstance(payload.get("name"), str):
            payload["name"] = transformer(payload["name"])
        for value in payload.values():
            transform_tool_uses(value, transformer)
    elif isinstance(payload, list):
        for item in payload:
            transform_tool_uses(item, transformer)


# --- System Prompt Patching ---

_system_prompt_patches_cache: list[dict] | None = None


def load_system_prompt_patches() -> list[dict]:
    """Load patches from config file specified by SYSTEM_PROMPT_PATCHES env var.

    Config format:
    {
      "replacements": [
        {"find": "...", "replace": "...", "required": true/false},
        ...
      ]
    }
    """
    global _system_prompt_patches_cache
    if _system_prompt_patches_cache is not None:
        return _system_prompt_patches_cache

    path = os.environ.get("SYSTEM_PROMPT_PATCHES")
    if not path:
        _system_prompt_patches_cache = []
        return _system_prompt_patches_cache

    if not os.path.exists(path):
        logger.warning("SYSTEM_PROMPT_PATCHES file not found: %s", path)
        _system_prompt_patches_cache = []
        return _system_prompt_patches_cache

    try:
        with open(path) as f:
            config = json.load(f)
        _system_prompt_patches_cache = config.get("replacements", [])
        logger.info("Loaded %d system prompt patches from %s", len(_system_prompt_patches_cache), path)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Failed to load system prompt patches from %s: %s", path, exc)
        _system_prompt_patches_cache = []

    return _system_prompt_patches_cache


def transform_system_prompt(payload: MutableMapping[str, Any]) -> None:
    """Apply configured patches to system prompt blocks.

    Raises HTTPException if a required patch fails to match.
    """
    patches = load_system_prompt_patches()
    if not patches:
        return

    system = payload.get("system")
    if not isinstance(system, list):
        return

    applied_count = 0
    for patch in patches:
        find_str = patch.get("find", "")
        replace_str = patch.get("replace", "")
        required = patch.get("required", False)

        if not find_str:
            continue

        found = False
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if find_str in text:
                    found = True
                    block["text"] = text.replace(find_str, replace_str)
                    applied_count += 1

        if required and not found:
            logger.error("Required system prompt patch failed to match: %s", find_str[:80])
            raise HTTPException(
                status_code=500,
                detail=f"Required system prompt patch failed: {find_str[:50]}..."
            )

    if applied_count > 0:
        logger.info("Applied %d system prompt patches", applied_count)


async def read_json_response(upstream: httpx.Response) -> JSONResponse:
    content = await upstream.aread()
    text = content.decode(upstream.encoding or "utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from upstream: {exc}") from exc

    if isinstance(payload, MutableMapping):
        transform_tool_choice(payload, add_mcp_prefix)
    transform_tool_uses(payload, add_mcp_prefix)
    return JSONResponse(
        content=payload,
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in {"content-length", "transfer-encoding", "content-encoding"}
        },
    )


def transform_sse_event(raw_event: str) -> str:
    if not raw_event:
        return raw_event

    lines = raw_event.splitlines()
    data_lines: List[str] = []
    prefix_lines: List[str] = []

    for line in lines:
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
        else:
            prefix_lines.append(line)

    if not data_lines:
        return raw_event

    raw_data = "\n".join(data_lines)
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        return raw_event

    if isinstance(payload, MutableMapping):
        transform_tool_choice(payload, add_mcp_prefix)
    transform_tool_uses(payload, add_mcp_prefix)
    new_data = json.dumps(payload, separators=(",", ":"))
    return "\n".join(prefix_lines + [f"data: {new_data}"])


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(60.0, connect=10.0, read=120.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def stream(self, *args: Any, **kwargs: Any):
        return self._client.stream(*args, **kwargs)


app = FastAPI()


async def get_client() -> HttpClient:
    client = getattr(app.state, "http_client", None)
    if client is None:
        raise RuntimeError("HTTP client not initialised")
    return client


@app.on_event("startup")
async def startup_event() -> None:
    app.state.http_client = HttpClient(get_upstream_url())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client = getattr(app.state, "http_client", None)
    if client is not None:
        await client.close()


@app.get("/health")
async def health() -> Response:
    return PlainTextResponse("ok")


@app.post("/v1/messages")
async def proxy_messages(request: Request, client: HttpClient = Depends(get_client)) -> Response:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON request: {exc}") from exc

    # Apply system prompt patches (identity reframing, etc.)
    transform_system_prompt(payload)

    if "tools" in payload and isinstance(payload["tools"], list):
        rewrite_tools_for_upstream(payload["tools"])
    if isinstance(payload, MutableMapping):
        transform_tool_choice(payload, strip_mcp_prefix)
    transform_tool_uses(payload.get("messages"), strip_mcp_prefix)

    headers = {k: v for k, v in request.headers.items()}
    for hop_header in ("host", "content-length", "accept-encoding", "content-encoding", "connection"):
        headers.pop(hop_header, None)
    ensure_beta_header(headers)

    tool_summaries: List[str] = []
    if isinstance(payload.get("tools"), list):
        for tool in payload["tools"]:
            if isinstance(tool, MutableMapping):
                name = tool.get("name")
                if isinstance(name, str):
                    tool_summaries.append(name)

    logger.info(
        "Forwarding /v1/messages stream=%s tools=%s",
        bool(payload.get("stream")),
        tool_summaries or ["<none>"],
    )

    stream_cm = client.stream(
        "POST",
        "/v1/messages",
        headers=headers,
        json=payload,
        params=request.query_params,
    )
    upstream = await stream_cm.__aenter__()
    streaming_response = False
    try:
        content_type = upstream.headers.get("content-type", "")
        if upstream.status_code >= 400 and "application/json" in content_type:
            return await read_json_response(upstream)

        if content_type.startswith("text/event-stream"):
            streaming_response = True
            buffer = ""
            logger.debug("Streaming response: %s", content_type)

            async def event_stream() -> AsyncIterator[bytes]:
                nonlocal buffer
                try:
                    async for chunk in upstream.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event, buffer = buffer.split("\n\n", 1)
                            transformed = transform_sse_event(event)
                            yield (transformed + "\n\n").encode("utf-8")
                finally:
                    if buffer:
                        transformed = transform_sse_event(buffer)
                        yield (transformed + "\n\n").encode("utf-8")
                    await stream_cm.__aexit__(None, None, None)

            response_headers = {
                k: v
                for k, v in upstream.headers.items()
                if k.lower() in {"content-type", "cache-control", "connection"}
            }
            return StreamingResponse(event_stream(), status_code=upstream.status_code, headers=response_headers)

        if "application/json" in content_type:
            return await read_json_response(upstream)

        raw_body = await upstream.aread()
        logger.info(
            "Upstream response status=%s content-type=%s stream=%s",
            upstream.status_code,
            content_type or "unknown",
            streaming_response,
        )
        return Response(
            content=raw_body,
            status_code=upstream.status_code,
            media_type=content_type or None,
            headers={k: v for k, v in upstream.headers.items() if k.lower() not in {"content-length"}},
        )
    finally:
        if not streaming_response:
            await stream_cm.__aexit__(None, None, None)


def create_app() -> FastAPI:
    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("PROXY_HOST", "127.0.0.1")
    port = int(os.environ.get("PROXY_PORT", "15041"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
