"""Remote MCP demo: HTTP server se (auth ke saath) connect, tools list/call, phir LLM agent.

Terminal 1:  python mcp_http_server.py
Terminal 2:  python main.py "add a note about the demo and search it"
             python main.py --offline                    # fake LLM, server still real HTTP
             python main.py --self-host --offline        # server bhi isi process mein (thread) start kar do
             python main.py --security-demo              # tool-poisoning audit dikhao
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "02-mcp-client-agent"))

from agentkit import get_llm  # noqa: E402

from mcp_bridge import MCPBridge  # noqa: E402
from mcp_client_agent import build_agent, confirm_destructive, offline_llm  # noqa: E402
from mcp_http_client import connect, http_transport  # noqa: E402
from mcp_http_server import DEFAULT_TOKEN, build_http_app  # noqa: E402
from mcp_security import audit_tools, build_malicious_server  # noqa: E402


def start_background_server(db: str, token: str):
    import uvicorn

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(build_http_app(db, token=token), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    return server, t, f"http://127.0.0.1:{port}/mcp"


async def raw_tour(url: str, token: str) -> None:
    async with connect(url, token) as c:
        print(f"connected over HTTP: protocol={c.protocol_version} server={c.server_info.name}")
        print("tools:", [t.name for t in (await c.list_tools()).tools])


def security_demo() -> None:
    async def go():
        from mcp import Client

        async with Client(build_malicious_server()) as c:
            tools = (await c.list_tools()).tools
        for f in audit_tools(tools):
            print(f"[BLOCK] {f.tool}: {f.reason}\n        ...{f.snippet}...")

    asyncio.run(go())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="Add a note titled 'HTTP demo' saying remote MCP works, then search for it.")
    ap.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    ap.add_argument("--token", default=os.getenv("MCP_TOKEN", DEFAULT_TOKEN))
    ap.add_argument("--offline", action="store_true", help="scripted fake LLM (no API key)")
    ap.add_argument("--self-host", action="store_true", help="start the HTTP server in a background thread")
    ap.add_argument("--security-demo", action="store_true")
    args = ap.parse_args()

    if args.security_demo:
        return security_demo()

    server = thread = None
    tmp = tempfile.TemporaryDirectory()
    if args.self_host:
        server, thread, args.url = start_background_server(os.path.join(tmp.name, "n.db"), args.token)
    try:
        asyncio.run(raw_tour(args.url, args.token))
        llm = offline_llm() if args.offline else get_llm()
        with MCPBridge({"notes": http_transport(args.url, args.token)}) as bridge:
            result = build_agent(llm, bridge, approve=confirm_destructive(bridge)).run(args.task)
            print("\n=== ANSWER ===\n" + result.output)
    finally:
        if server:
            server.should_exit = True
            thread.join(5)
        tmp.cleanup()


if __name__ == "__main__":
    main()
