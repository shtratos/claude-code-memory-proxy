#!/usr/bin/env bash
#
# Drives a three-step Claude Code memory scenario against the local proxy.
# - Creates an isolated memories directory
# - Generates a Claude settings / MCP config pointed at the local memory proxy
# - Runs three non-interactive prompts with approvals bypassed
#
# Optional: export HTTP(S)_PROXY / NO_PROXY / SSL_CERT_FILE before running if you
# want to capture traffic with mitmproxy. This script does not set those values by default.

set -euo pipefail

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI not found on PATH" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

timestamp="$(date -u +%Y-%m-%d-%H%M%S)"
scenario_root="${REPO_ROOT}/data/random-access-memories/${timestamp}"
memories_dir="${scenario_root}/memories"
mkdir -p "${memories_dir}"

config_path="${scenario_root}/claude-config.json"
log_path="${scenario_root}/claude-transcript.log"

# Allow overriding token/base URL via env, otherwise fall back to local defaults.
proxy_base_url="${ANTHROPIC_BASE_URL:-http://127.0.0.1:15041}"
model_name="${CLAUDE_MODEL:-claude-sonnet-4-5}"

python3 - <<'PY' "${config_path}" "${memories_dir}" "${proxy_base_url}"
import json
import os
import sys

config_path, memories_dir, proxy_base_url = sys.argv[1:4]

env = {
    "ANTHROPIC_BASE_URL": proxy_base_url,
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_COST_WARNINGS": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_TELEMETRY": "1",
    "MEMORY_DIR": memories_dir,
}

for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BETA"):
    value = os.environ.get(key)
    if value:
        env[key] = value

config = {
    "env": env,
    "mcpServers": {
        "memory": {
            "command": "uv",
            "args": ["run", "memory-server"],
            "env": {
                "MEMORY_DIR": memories_dir,
            },
        }
    }
}

with open(config_path, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2)
    fh.write("\n")
PY

echo "Created scenario config at ${config_path}"
echo "Memories will be stored in ${memories_dir}"
echo "Transcript will be recorded in ${log_path}"
echo

run_prompt() {
  local label="$1"
  local prompt="$2"
  echo ">>> Running prompt [${label}]"
  echo ">>> ${prompt}" | tee -a "${log_path}"
  claude \
    --settings "${config_path}" \
    --mcp-config "${config_path}" \
    --strict-mcp-config \
    --dangerously-skip-permissions \
    --print \
    --output-format text \
    --model "${model_name}" \
    "${prompt}" | tee -a "${log_path}"
  echo >> "${log_path}"
}

run_prompt "memory-view" "I need to solve a customer issue, how do I do this?"
run_prompt "memory-store" "When you want to run tests in this project, you should always prefix all commands with \`uv run\` - worth remembering this."
run_prompt "memory-recall" "I'm running my script like this: \`python main.py\` - but it says something like python not found. how do I fix this?"

echo "Scenario complete. Review:"
echo "  Config:     ${config_path}"
echo "  Transcript: ${log_path}"
echo "  Memories:   ${memories_dir}"
echo
echo "Troubleshooting tips:"
echo "  - If requests fail with 4xx, verify ANTHROPIC_API_KEY, ANTHROPIC_BETA, and model availability."
echo "  - To capture traffic with mitmproxy, export HTTP(S)_PROXY / NO_PROXY and any certificate bundles before running this script."
