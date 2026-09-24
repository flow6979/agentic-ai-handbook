"""SDK ke bina MCP: server ko subprocess mein chalao aur stdin/stdout pe khud JSON-RPC likho.

Isse samajh aata hai ki MCP 'magic' nahi hai: newline-delimited JSON-RPC 2.0 messages hain.
Hum handshake-era flow (protocol 2025-11-25) dikhate hain kyunki woh sabse zyada
hosts aaj bhi bolte hain:

    client -> initialize                 (main kaun hoon, kya capabilities hain, kaunsa version)
    server -> result                     (server info + capabilities + chosen version)
    client -> notifications/initialized  (ho gaya, ab kaam shuru)
    client -> tools/list
    client -> tools/call
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROTOCOL = "2025-11-25"


def run_raw(db_path: str, verbose: bool = True) -> list[dict]:
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "mcp_notes_server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env={**os.environ, "NOTES_DB": db_path},
    )
    responses: list[dict] = []

    def send(msg: dict) -> None:
        line = json.dumps(msg)
        if verbose:
            print(f"--> {line}")
        proc.stdin.write(line + "\n")  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def recv() -> dict:
        while True:
            line = proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                raise RuntimeError("server closed stdout")
            msg = json.loads(line)
            if "id" in msg:  # notifications (logs etc.) skip karo, sirf responses chahiye
                if verbose:
                    print(f"<-- {line.strip()[:500]}\n")
                responses.append(msg)
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "raw-demo", "version": "0.1"},
        }})
        recv()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})  # notification: id nahi, response nahi aata
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        recv()
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "add_note", "arguments": {"title": "raw", "body": "hello from raw JSON-RPC"}}})
        recv()
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}})
        recv()
    finally:
        proc.stdin.close()  # type: ignore[union-attr]
        proc.wait(timeout=10)
    return responses


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        run_raw(os.path.join(d, "notes.sqlite3"))
