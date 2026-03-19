"""Emacs MCP Server - bridges Claude Code to a running Emacs instance."""
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0"]
# ///

import asyncio
import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("emacs-mcp")

EMACS_HOST = "127.0.0.1"
EMACS_PORT = 9377

mcp = FastMCP("emacs")


class EmacsConnection:
    """Persistent TCP connection to the Emacs MCP bridge."""

    def __init__(self, host: str = EMACS_HOST, port: int = EMACS_PORT):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port
        )
        log.info("Connected to Emacs at %s:%d", self.host, self.port)

    async def ensure_connected(self) -> None:
        if self.writer is None or self.writer.is_closing():
            await self.connect()

    async def request(self, method: str, **params) -> dict:
        async with self._lock:
            await self.ensure_connected()
            msg = json.dumps({"method": method, "params": params, "id": 1})
            self.writer.write((msg + "\n").encode())
            await self.writer.drain()
            line = await asyncio.wait_for(self.reader.readline(), timeout=10.0)
            return json.loads(line.decode())

    async def close(self) -> None:
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()


emacs = EmacsConnection()


@mcp.tool()
async def eval_elisp(expression: str) -> str:
    """Evaluate an arbitrary Emacs Lisp expression in the running Emacs instance.

    Args:
        expression: The Elisp expression to evaluate (e.g. "(+ 1 2)" or "(buffer-name)")
    """
    resp = await emacs.request("eval", expression=expression)
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    return result.get("value", str(result))


@mcp.tool()
async def open_file(path: str, line: int | None = None) -> str:
    """Open a file in Emacs in a new frame.

    Args:
        path: Absolute path to the file to open
        line: Optional line number to jump to
    """
    params = {"path": path}
    if line is not None:
        params["line"] = line
    resp = await emacs.request("open_file", **params)
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    return f"Opened {result.get('opened', path)}"


@mcp.tool()
async def insert_to_scratch(text: str) -> str:
    """Insert text into the Emacs *scratch* buffer, replacing its contents.
    Opens the scratch buffer in a new frame. Used for email drafting workflow.

    Args:
        text: The text to insert into the scratch buffer
    """
    resp = await emacs.request("insert_scratch", text=text)
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    return "Text inserted into *scratch* buffer"


@mcp.tool()
async def get_buffer_content(buffer: str) -> str:
    """Read the contents of a named Emacs buffer.

    Args:
        buffer: Name of the buffer (e.g. "*scratch*" or "init.el")
    """
    resp = await emacs.request("get_buffer_content", buffer=buffer)
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    return result.get("content", "")


@mcp.tool()
async def list_buffers() -> str:
    """List all open Emacs buffers with their file paths and modification status."""
    resp = await emacs.request("list_buffers")
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    buffers = result.get("buffers", [])
    lines = []
    for b in buffers:
        mod = " [modified]" if b.get("modified") else ""
        file_info = f" ({b['file']})" if b.get("file") else ""
        lines.append(f"  {b['name']}{file_info}{mod}")
    return f"Open buffers ({len(buffers)}):\n" + "\n".join(lines)


@mcp.tool()
async def get_selection() -> str:
    """Get the currently selected text (active region) in Emacs."""
    resp = await emacs.request("get_selection")
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    sel = result.get("selection")
    if sel is None:
        return "No active selection"
    return sel


@mcp.tool()
async def save_buffer(buffer: str | None = None) -> str:
    """Save an Emacs buffer. If no buffer name is given, saves the current buffer.

    Args:
        buffer: Optional name of the buffer to save
    """
    params = {}
    if buffer is not None:
        params["buffer"] = buffer
    resp = await emacs.request("save_buffer", **params)
    result = resp.get("result", {})
    if "error" in resp:
        return f"Error: {resp['error'].get('message', str(resp['error']))}"
    return f"Saved {result.get('saved', 'buffer')}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
