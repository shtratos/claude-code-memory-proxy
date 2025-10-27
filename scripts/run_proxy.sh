#!/usr/bin/env bash
# Launch the memory proxy.
# Optionally set HTTP(S)_PROXY / NO_PROXY in the environment before invoking
# this script if you want to route traffic through an intermediary (e.g. mitmproxy).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

: "${UPSTREAM_API_URL:=https://api.anthropic.com}"
: "${PROXY_PORT:=15041}"

exec env UPSTREAM_API_URL="$UPSTREAM_API_URL" PROXY_PORT="$PROXY_PORT" uv run memory-proxy
