"""Notes server ka 'tour': SDK client se server launch karo (stdio) aur har primitive try karo.

    python main.py            # server subprocess launch hoga, tools/resources/prompts list + call
    python main.py --offline  # same (is demo mein LLM hai hi nahi, sab offline chalta hai)
    python main.py --raw      # SDK ke bina, raw JSON-RPC lines dekhne ke liye (raw_jsonrpc_demo.py)

Yeh LLM use nahi karta: sirf dikhata hai ki MCP client-server wire pe kya hota hai.
LLM wala agent 02-mcp-client-agent mein hai.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

from mcp import Client, StdioServerParameters

HERE = os.path.dirname(os.path.abspath(__file__))


async def tour(db_path: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(HERE, "mcp_notes_server.py")],
        env={"NOTES_DB": db_path},
    )
    async with Client(params) as c:
        print(f"connected: server={c.server_info.name} protocol={c.protocol_version}")
        print(f"instructions: {c.instructions}\n")

        tools = (await c.list_tools()).tools
        print("TOOLS (model-controlled):")
        for t in tools:
            hints = t.annotations.model_dump(exclude_none=True) if t.annotations else {}
            print(f"  - {t.name}: {t.description}  hints={hints}")

        r = await c.call_tool("add_note", {"title": "Buy milk", "body": "2 litres", "tags": ["todo", "home"]})
        print("\ncall add_note ->", r.content[0].text)
        r = await c.call_tool("add_note", {"title": "MCP talk", "body": "prepare slides on MCP", "tags": ["work"]})
        print("call add_note ->", r.content[0].text)
        r = await c.call_tool("search_notes", {"query": "mcp"})
        print("call search_notes('mcp') ->", r.content[0].text)
        r = await c.call_tool("mark_done", {"note_id": 999})
        print(f"call mark_done(999) -> is_error={r.is_error} text={r.content[0].text!r}")

        print("\nRESOURCES (app-controlled):")
        for res in (await c.list_resources()).resources:
            print(f"  - {res.uri} ({res.mime_type})")
        for tpl in (await c.list_resource_templates()).resource_templates:
            print(f"  - template {tpl.uri_template}")
        print("read notes://1 ->", (await c.read_resource("notes://1")).contents[0].text)

        print("\nPROMPTS (user-controlled):")
        for p in (await c.list_prompts()).prompts:
            args = [a.name for a in (p.arguments or [])]
            print(f"  - {p.name}{args}: {p.description}")
        msg = (await c.get_prompt("weekly_review", {})).messages[0]
        print("get_prompt weekly_review ->\n" + msg.content.text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="accepted for consistency; this demo never calls an LLM")
    ap.add_argument("--raw", action="store_true", help="show raw JSON-RPC over stdio without the SDK client")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "notes.sqlite3")
        if args.raw:
            from raw_jsonrpc_demo import run_raw

            run_raw(db)
        else:
            asyncio.run(tour(db))


if __name__ == "__main__":
    main()
