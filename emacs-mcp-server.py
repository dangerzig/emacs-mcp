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
        self._next_id = 0

    async def _close_connection(self) -> None:
        """Close the current connection and reset state."""
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except OSError:
                pass
        self.reader = None
        self.writer = None

    async def connect(self) -> None:
        await self._close_connection()
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
            self._next_id += 1
            msg = json.dumps({"method": method, "params": params, "id": self._next_id})
            try:
                self.writer.write((msg + "\n").encode())
                await self.writer.drain()
                line = await asyncio.wait_for(self.reader.readline(), timeout=10.0)
                if not line:
                    raise ConnectionError("Connection closed by Emacs")
                return json.loads(line.decode())
            except Exception:
                await self._close_connection()
                raise

    async def close(self) -> None:
        await self._close_connection()


emacs = EmacsConnection()


def _extract_error(resp: dict) -> str | None:
    """Return an error message from a response, or None if no error."""
    if "error" in resp:
        err = resp["error"]
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    result = resp.get("result", {})
    if isinstance(result, dict) and "error" in result:
        return str(result["error"])
    return None


@mcp.tool()
async def eval_elisp(expression: str) -> str:
    """Evaluate an arbitrary Emacs Lisp expression in the running Emacs instance.

    Args:
        expression: The Elisp expression to evaluate (e.g. "(+ 1 2)" or "(buffer-name)")
    """
    resp = await emacs.request("eval", expression=expression)
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    return resp.get("result", {}).get("value", str(resp.get("result")))


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
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    return f"Opened {resp.get('result', {}).get('opened', path)}"


@mcp.tool()
async def insert_to_scratch(text: str) -> str:
    """Insert text into the Emacs *scratch* buffer, replacing its contents.
    Opens the scratch buffer in a new frame. Used for email drafting workflow.

    Args:
        text: The text to insert into the scratch buffer
    """
    resp = await emacs.request("insert_scratch", text=text)
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    return "Text inserted into *scratch* buffer"


@mcp.tool()
async def get_buffer_content(buffer: str) -> str:
    """Read the contents of a named Emacs buffer.

    Args:
        buffer: Name of the buffer (e.g. "*scratch*" or "init.el")
    """
    resp = await emacs.request("get_buffer_content", buffer=buffer)
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    return resp.get("result", {}).get("content", "")


@mcp.tool()
async def list_buffers() -> str:
    """List all open Emacs buffers with their file paths and modification status."""
    resp = await emacs.request("list_buffers")
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    buffers = resp.get("result", {}).get("buffers", [])
    lines = []
    for b in buffers:
        mod = " [modified]" if b.get("modified") else ""
        path = b.get("file")
        file_info = f" ({path})" if path else ""
        lines.append(f"  {b.get('name', '???')}{file_info}{mod}")
    return f"Open buffers ({len(buffers)}):\n" + "\n".join(lines)


@mcp.tool()
async def get_selection() -> str:
    """Get the currently selected text (active region) in Emacs."""
    resp = await emacs.request("get_selection")
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    sel = resp.get("result", {}).get("selection")
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
    err = _extract_error(resp)
    if err:
        return f"Error: {err}"
    return f"Saved {resp.get('result', {}).get('saved', 'buffer')}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
