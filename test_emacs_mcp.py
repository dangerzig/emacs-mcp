"""End-to-end tests for emacs-mcp.

Requires a running Emacs with emacs-mcp-bridge loaded on port 9377.
Run with: python3 test_emacs_mcp.py
"""

import asyncio
import json
import sys

HOST = "127.0.0.1"
PORT = 9377
_next_id = 0


async def request(reader, writer, method, **params):
    global _next_id
    _next_id += 1
    msg = json.dumps({"method": method, "params": params, "id": _next_id})
    writer.write((msg + "\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=10.0)
    if not line:
        raise ConnectionError("Connection closed")
    return json.loads(line.decode())


def extract_error(resp):
    if "error" in resp:
        err = resp["error"]
        return err.get("message", str(err)) if isinstance(err, dict) else str(err)
    result = resp.get("result", {})
    if isinstance(result, dict) and "error" in result:
        return str(result["error"])
    return None


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  PASS  {name}")

    def fail(self, name, detail):
        self.failed += 1
        self.errors.append((name, detail))
        print(f"  FAIL  {name}: {detail}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed", end="")
        if self.failed:
            print(f", {self.failed} FAILED")
            for name, detail in self.errors:
                print(f"  - {name}: {detail}")
        else:
            print()


async def run_tests():
    t = TestResult()

    try:
        reader, writer = await asyncio.open_connection(HOST, PORT)
    except ConnectionRefusedError:
        print("ERROR: Cannot connect to Emacs MCP bridge on port 9377.")
        print("Make sure Emacs is running with (emacs-mcp-start).")
        sys.exit(1)

    print("Connected to Emacs MCP bridge.\n")

    # --- eval ---
    print("eval:")
    resp = await request(reader, writer, "eval", expression="(+ 2 3)")
    if resp.get("result", {}).get("value") == "5":
        t.ok("basic arithmetic")
    else:
        t.fail("basic arithmetic", f"expected '5', got {resp}")

    resp = await request(reader, writer, "eval", expression='(format "hello %s" "world")')
    val = resp.get("result", {}).get("value", "")
    if "hello world" in val:
        t.ok("string formatting")
    else:
        t.fail("string formatting", f"expected 'hello world' in result, got {val}")

    resp = await request(reader, writer, "eval", expression="(/ 1 0)")
    err = extract_error(resp)
    if err:
        t.ok("division by zero returns error")
    else:
        t.fail("division by zero returns error", f"expected error, got {resp}")

    resp = await request(reader, writer, "eval", expression="(undefined-function-xyz)")
    err = extract_error(resp)
    if err:
        t.ok("undefined function returns error")
    else:
        t.fail("undefined function returns error", f"expected error, got {resp}")

    # --- list_buffers ---
    print("\nlist_buffers:")
    resp = await request(reader, writer, "list_buffers")
    buffers = resp.get("result", {}).get("buffers", [])
    if len(buffers) > 0:
        t.ok(f"returns buffers ({len(buffers)} found)")
    else:
        t.fail("returns buffers", "empty list")

    scratch = [b for b in buffers if b.get("name") == "*scratch*"]
    if scratch:
        t.ok("*scratch* buffer present")
    else:
        t.fail("*scratch* buffer present", "not found in buffer list")

    b = buffers[0]
    if "name" in b and "file" in b and "modified" in b:
        t.ok("buffer entries have expected fields")
    else:
        t.fail("buffer entries have expected fields", f"got keys: {list(b.keys())}")

    hidden = [b for b in buffers if b.get("name", "").startswith(" ")]
    if not hidden:
        t.ok("hidden buffers filtered out")
    else:
        t.fail("hidden buffers filtered out", f"found {len(hidden)} hidden buffers")

    # --- insert_scratch + get_buffer_content ---
    print("\ninsert_scratch + get_buffer_content:")
    # Record frames before so we can close any new ones
    resp = await request(reader, writer, "eval", expression="(length (frame-list))")
    frames_before_scratch = int(resp.get("result", {}).get("value", "0"))
    test_text = "emacs-mcp test marker 7e3f9a"
    resp = await request(reader, writer, "insert_scratch", text=test_text)
    if resp.get("result", {}).get("inserted"):
        t.ok("insert_scratch succeeds")
    else:
        t.fail("insert_scratch succeeds", f"got {resp}")

    resp = await request(reader, writer, "get_buffer_content", buffer="*scratch*")
    content = resp.get("result", {}).get("content", "")
    if content == test_text:
        t.ok("get_buffer_content reads back inserted text")
    else:
        t.fail("get_buffer_content reads back inserted text", f"expected {test_text!r}, got {content!r}")

    # Clean up: close any frame insert_scratch opened
    await request(reader, writer, "eval", expression=f"""
        (let ((n (length (frame-list))))
          (when (> n {frames_before_scratch})
            (delete-frame)))
    """)

    # --- get_buffer_content error ---
    print("\nget_buffer_content error:")
    resp = await request(reader, writer, "get_buffer_content", buffer="*nonexistent-test-buffer-xyz*")
    err = extract_error(resp)
    if err and "not found" in err.lower():
        t.ok("nonexistent buffer returns error")
    else:
        t.fail("nonexistent buffer returns error", f"expected 'not found' error, got {resp}")

    # --- get_selection ---
    print("\nget_selection:")
    resp = await request(reader, writer, "get_selection")
    result = resp.get("result", {})
    err = extract_error(resp)
    if not err:
        t.ok("get_selection returns without error")
    else:
        t.fail("get_selection returns without error", f"got error: {err}")

    # --- save_buffer errors ---
    print("\nsave_buffer:")
    resp = await request(reader, writer, "save_buffer", buffer="*nonexistent-test-buffer-xyz*")
    err = extract_error(resp)
    if err and "not found" in err.lower():
        t.ok("nonexistent buffer returns error")
    else:
        t.fail("nonexistent buffer returns error", f"expected 'not found' error, got {resp}")

    resp = await request(reader, writer, "save_buffer", buffer="*scratch*")
    err = extract_error(resp)
    if err and "no file" in err.lower():
        t.ok("buffer without file returns error")
    else:
        t.fail("buffer without file returns error", f"expected 'no file' error, got {resp}")

    # --- open_file ---
    print("\nopen_file:")
    resp = await request(reader, writer, "eval", expression="(length (frame-list))")
    frames_before_open = int(resp.get("result", {}).get("value", "0"))
    resp = await request(reader, writer, "open_file", path="/Users/danzigmond/emacs-mcp/emacs-mcp-server.py", line=1)
    result = resp.get("result", {})
    if result.get("opened"):
        t.ok("open_file succeeds")
    else:
        t.fail("open_file succeeds", f"got {resp}")

    # Clean up: close the frame open_file created
    await request(reader, writer, "eval", expression=f"""
        (let ((n (length (frame-list))))
          (when (> n {frames_before_open})
            (delete-frame)))
    """)

    # --- unknown method ---
    print("\nunknown method:")
    resp = await request(reader, writer, "bogus_method")
    err = extract_error(resp)
    if err and "unknown" in err.lower():
        t.ok("unknown method returns error")
    else:
        t.fail("unknown method returns error", f"expected 'unknown' error, got {resp}")

    # --- response ids ---
    print("\nprotocol:")
    resp = await request(reader, writer, "eval", expression="t")
    if resp.get("id") == _next_id:
        t.ok("response id matches request id")
    else:
        t.fail("response id matches request id", f"expected {_next_id}, got {resp.get('id')}")

    writer.close()
    await writer.wait_closed()

    t.summary()
    sys.exit(1 if t.failed else 0)


if __name__ == "__main__":
    asyncio.run(run_tests())
