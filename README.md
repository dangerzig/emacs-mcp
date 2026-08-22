# emacs-mcp

An [MCP](https://modelcontextprotocol.io/) server that bridges [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to a running Emacs instance via a persistent TCP connection.

Replaces the `emacsclient` approach with a ~25-30x faster persistent socket connection.

## Architecture

```
Claude Code <--stdio/JSON-RPC--> Python MCP Server <--TCP--> Emacs
```

- **Python MCP server** (`emacs-mcp-server.py`): Speaks MCP over stdio to Claude Code, relays requests to Emacs over TCP.
- **Emacs TCP server** (`emacs-mcp-bridge.el`): Listens on port 9377, handles JSON requests, returns JSON responses.

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

Either load the provided file:

```elisp
(add-to-list 'load-path "/path/to/emacs-mcp")
(require 'emacs-mcp-bridge)
(emacs-mcp-start)
```

Or copy the contents of `emacs-mcp-bridge.el` directly into your `init.el`.

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

## Companion: named Claude sessions in vterm (`claude-sessions.el`)

An optional Emacs Lisp companion for people who run [Claude Code](https://docs.anthropic.com/en/docs/claude-code) inside [vterm](https://github.com/akermu/emacs-libvterm) buffers. It solves two everyday annoyances:

1. **Sessions survive a crash by name.** If Emacs dies, the live `claude` processes are killed. The conversations aren't lost (Claude Code writes a transcript per session), but matching an opaque session UUID back to "the buffer I called `email`" is painful. This file records a `name -> session-id -> directory` mapping in a small TSV registry (`~/.claude/vterm-sessions.tsv`) at launch time, using a pre-minted id (`claude --session-id`), so you reopen a session **by name** and it resumes where it stopped.
2. **A real editor for your prompt.** The live vterm prompt sends keystrokes straight to Claude, so Emacs editing (transpose, kill-ring, flyspell) can't touch that line. `C-c e` pops a `text-mode` compose buffer with full Emacs editing, then ships the text to the session as a bracketed paste.

### Key bindings

| Keys | Command | What it does |
|------|---------|--------------|
| `C-c c n` | `my/claude-new-frame` | New **named** session in its own frame; logs it to the registry. The default way to start. |
| `C-c c r` | `my/claude-resume-named` | Reopen a registered session **by name** (`claude --resume`). The default way to restart. |
| `C-c c R` | `my/claude-code-resume` | `claude --continue` (most recent; rarely useful with many sessions). |
| `C-c c c` | `my/claude-code` | New unnamed session in the current window. |
| `C-c e` | `my/claude-compose` | In a `claude-*` buffer, open the compose buffer (`C-c C-c` send, `C-c C-k` cancel). |

### Setup

```elisp
(add-to-list 'load-path "/path/to/emacs-mcp")
(require 'claude-sessions)   ;; requires the `vterm' package and the `claude' CLI
```

A printable one-page cheat sheet is included: [`claude-cheatsheet.pdf`](claude-cheatsheet.pdf) (source `claude-cheatsheet.md`, rebuilt with `pandoc claude-cheatsheet.md -o claude-cheatsheet.pdf --pdf-engine=xelatex -V mainfont="Times New Roman" -H cheatsheet-header.tex`).

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (handles dependencies automatically via inline script metadata)
- Emacs 27+ (for built-in `json.el`)
- For `claude-sessions.el`: the `vterm` package and the `claude` CLI on your `PATH`

## License

MIT

## Author

Dan Zigmond ([@dangerzig](https://github.com/dangerzig)) - [shmonk.com](https://shmonk.com)
