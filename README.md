# emacs-mcp

An [MCP](https://modelcontextprotocol.io/) server that bridges [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to a running Emacs instance via a persistent TCP connection.

Replaces the `emacsclient` approach with a ~25-30x faster persistent socket connection.

## Architecture

```
Claude Code <--stdio/JSON-RPC--> Python MCP Server <--TCP--> Emacs
```

- **Python MCP server** (`emacs-mcp-server.py`): Speaks MCP over stdio to Claude Code, relays requests to Emacs over TCP.
- **Emacs TCP server** (Elisp, added to `init.el`): Listens on port 9377, handles JSON requests, returns JSON responses.

## Tools

| Tool | Description |
|------|-------------|
| `eval_elisp` | Evaluate arbitrary Emacs Lisp |
| `open_file` | Open a file in a new frame (optional line number) |
| `insert_to_scratch` | Insert text into `*scratch*` buffer |
| `get_buffer_content` | Read contents of a named buffer |
| `list_buffers` | List open buffers with file paths and modification status |
| `get_selection` | Get the currently selected text (active region) |
| `save_buffer` | Save a buffer by name (or current buffer) |

## Setup

### 1. Add the Elisp TCP server to your Emacs config

Add the contents of the TCP server section to your `init.el`. This creates a listener on `127.0.0.1:9377` that handles JSON requests from the Python MCP server. See the project wiki or source for the full Elisp code.

### 2. Register with Claude Code

```bash
claude mcp add --transport stdio --scope user emacs -- \
  uv run /path/to/emacs-mcp/emacs-mcp-server.py
```

### 3. (Optional) Auto-allow all tools

Add the MCP tool names to the `allow` list in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__emacs__eval_elisp",
      "mcp__emacs__open_file",
      "mcp__emacs__insert_to_scratch",
      "mcp__emacs__get_buffer_content",
      "mcp__emacs__list_buffers",
      "mcp__emacs__get_selection",
      "mcp__emacs__save_buffer"
    ]
  }
}
```

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (handles dependencies automatically via inline script metadata)
- Emacs with `json.el` (included in Emacs 27+)
