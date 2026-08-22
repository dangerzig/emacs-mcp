# Claude in Emacs: Cheat Sheet

Custom commands for running and editing Claude Code sessions inside Emacs vterm buffers. Claude sessions are named `claude-<name>`; plain terminals are `vterm-<name>`.

## Starting and restarting a session

| Keys | What it does | When to use |
|------|--------------|-------------|
| `C-c c n` | **New named session** in its own frame (`claude-<name>`). Prompts for a name, pins a session id, logs it to the registry. | Your default. Always start this way so sessions are recoverable by name. |
| `C-c c r` | **Reopen a past session by name** (tab-complete from the registry), via `claude --resume`. | After a crash or quit, to bring a session back. The one you will actually use. |
| `C-c c R` | Resume the **most recent** conversation (`claude --continue`), in the current window. | Rarely useful when many sessions are running. |
| `C-c c c` | New session in the current window, **unnamed and not registered**. | Rarely. The bare, old way. |
| `C-c t` | Named plain (non-Claude) terminal in a new frame. | Any ordinary shell work. |

## Editing and sending input to Claude

| Keys | What it does |
|------|--------------|
| `C-c e` | In a `claude-*` buffer: open `*claude-compose*`, a real text buffer with full Emacs editing (transpose, kill-ring, spellcheck, and so on). |
| `C-c C-c` | In the compose buffer: send the text to the session (bracketed paste, keeps newlines) and submit. |
| `C-c C-k` | In the compose buffer: cancel without sending. |
| `C-c C-v` | Enter `vterm-copy-mode`: read-only, navigate, search, and copy the output like a normal buffer. Press `q` to exit. |

## Copy and paste inside a session

| Keys | What it does |
|------|--------------|
| `M-c` | Copy (kill-ring-save) |
| `M-v` | Paste (vterm-aware yank) |
| `M-x` | Cut (kill-region) |
| `M-l` | Run an Emacs command (`execute-extended-command`) |

## Mnemonics and notes

- The `c` prefix means Claude: **n**ew, lowercase **r** to **r**eopen a named session (the common one), capital **R** for **R**ecent (`claude --continue`, rarely used), and the standalone `e` for **e**dit/compose.
- The live Claude prompt is a terminal, so keystrokes go straight to Claude and Emacs editing cannot touch that line in place. Use `C-c e` (compose buffer) for real Emacs editing.
- The session registry lives at `~/.claude/vterm-sessions.tsv` (one line per named session: name, id, directory, timestamp).
- After a crash, sessions started with `C-c c n` come back by name via `C-c c r`. Sessions started the bare way are recoverable only by grepping `~/.claude/projects/`.
