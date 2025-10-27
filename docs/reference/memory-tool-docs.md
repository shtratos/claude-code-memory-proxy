# Memory Tool (Reference)

*Source: Anthropic documentation. Included here so the project’s requirements and examples stay close at hand. Remove or update if the upstream documentation changes.*

The memory tool enables Claude to store and retrieve information across conversations through a memory file directory. Claude can create, read, update, and delete files that persist between sessions, allowing it to build knowledge over time without keeping everything in the context window.

The memory tool operates client-side—you control where and how the data is stored through your own infrastructure.

> **Beta note**: Use the beta header `context-management-2025-06-27` to enable this feature. Share feedback via Anthropic’s [memory tool feedback form](https://forms.gle/YXC2EKGMhjN1c4L88).

## Use cases

- Maintain project context across multiple agent executions
- Learn from past interactions, decisions, and feedback
- Build knowledge bases over time
- Enable cross-conversation learning where Claude improves at recurring workflows

## Operational Overview

When enabled, Claude automatically checks its memory directory before starting tasks. Claude issues tool calls for memory operations, and the client executes those operations locally. Keep all memory operations confined to `/memories` for security.

Example sequence (simplified):

1. User asks for help → Claude checks memory directory.
2. Claude issues a `view` command on `/memories`.
3. Client returns directory contents.
4. Claude reads relevant files (additional `view` calls).
5. Client returns file contents.
6. Claude uses retrieved context to respond.

## Supported Models (per documentation)

- Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
- Claude Sonnet 4 (`claude-sonnet-4-20250514`)
- Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Claude Opus 4.1 (`claude-opus-4-1-20250805`)
- Claude Opus 4 (`claude-opus-4-20250514`)

## Using the Tool

1. Include the beta header `context-management-2025-06-27` in API requests.
2. Advertise the memory tool in the `tools` array.
3. Implement handlers for each memory command.

Anthropic’s SDKs provide helpers:

- Python: subclass `BetaAbstractMemoryTool`.
- TypeScript: use `betaMemoryTool`.

### Example cURL Request

```bash
curl https://api.anthropic.com/v1/messages \
  --header "x-api-key: $ANTHROPIC_API_KEY" \
  --header "anthropic-version: 2023-06-01" \
  --header "content-type: application/json" \
  --header "anthropic-beta: context-management-2025-06-27" \
  --data '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 2048,
    "tools": [
      {
        "type": "memory_20250818",
        "name": "memory"
      }
    ],
    "messages": [
      {
        "role": "user",
        "content": "I'm drafting a follow-up response. What did we promise the customer?"
      }
    ]
  }'
```

The resulting `tool_use` call might look like:

```json
{
  "type": "tool_use",
  "id": "toolu_01C4D5E6F7G8H9I0J1K2L3M4",
  "name": "memory",
  "input": {
    "command": "view",
    "path": "/memories"
  }
}
```

Your application must respond with the appropriate `tool_result`, either listing directory contents or returning file text. Additional commands (`create`, `insert`, `str_replace`, `delete`, `rename`) follow similar patterns.

## Command Summary

| Command | Purpose |
| --- | --- |
| `view` | List directory contents or read file text. Supports `view_range` with 1-based start and end (use `-1` for “rest of file”). |
| `create` | Create a new file with the provided text. |
| `str_replace` | Replace occurrences of `old_str` with `new_str` in a file. |
| `insert` | Insert text at a given line number (1-based in the spec; confirm your implementation’s indexing). |
| `delete` | Delete the specified file. |
| `rename` | Rename or move a file within `/memories`. |
| `clear_all_memory` | Optional command to delete all memories (implement if desired). |

## Path Safety Considerations

- Reject paths not starting with `/memories`.
- Resolve paths (`Path.resolve()`) and ensure they stay within the memory root.
- Skip hidden files when listing directories (optional but recommended).
- Handle errors gracefully—surface clear error messages without stack traces.

## Integration with Context Editing

The memory tool can be used alongside context editing so Claude can summarize and persist important information before tool results are trimmed from the conversation. Combine `tools` (memory) with `context_management` edits (e.g., `clear_tool_uses_20250919`) to handle long workflows.

Example excerpt (Python):

```python
response = client.beta.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=4096,
    messages=[...],
    tools=[{
        "type": "memory_20250818",
        "name": "memory"
    }],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 100000},
                "keep": {"type": "tool_uses", "value": 3}
            }
        ]
    }
)
```

Adjust thresholds and exclusions as needed (for example, exclude memory tool uses from clearing).

## Error Handling

Follow the same patterns as other tool integrations: return clear error messages (file not found, permission errors, invalid paths). Sanitize user input before writing to disk.

## Additional Resources

- [Anthropic memory tool documentation](https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool)
- [SDK examples](https://github.com/anthropics/anthropic-sdk-python/tree/main/examples/memory)
- [Claude Code overview](https://docs.claude.com/en/docs/claude-code/overview)

Keep this document in sync with official updates to avoid divergence from the upstream specification.
