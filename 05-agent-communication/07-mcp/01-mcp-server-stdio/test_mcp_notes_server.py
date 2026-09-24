"""Offline tests: in-process (fast) + ek real stdio subprocess + raw JSON-RPC."""
import asyncio
import json
import os
import sys

from mcp import Client, StdioServerParameters

from mcp_notes_server import build_server
from raw_jsonrpc_demo import run_raw

HERE = os.path.dirname(os.path.abspath(__file__))


def run(coro):
    return asyncio.run(coro)


def test_tools_resources_prompts_in_process(tmp_path):
    server = build_server(str(tmp_path / "n.db"))

    async def go():
        # Client ko MCPServer object do -> in-process connection (no subprocess, no network). Tests ke liye best.
        async with Client(server) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert names == {"add_note", "search_notes", "mark_done", "delete_note"}

            r = await c.call_tool("add_note", {"title": "Buy milk", "body": "2L", "tags": ["todo"]})
            note = json.loads(r.content[0].text)
            assert note["id"] == 1 and note["tags"] == ["todo"]

            found = json.loads((await c.call_tool("search_notes", {"query": "milk"})).content[0].text)
            assert [n["id"] for n in found] == [1]

            assert (await c.call_tool("mark_done", {"note_id": 1})).is_error is False
            bad = await c.call_tool("mark_done", {"note_id": 42})
            assert bad.is_error and "does not exist" in bad.content[0].text  # ToolError message reaches the model

            # resources: static + template
            assert [str(r.uri) for r in (await c.list_resources()).resources] == ["notes://all"]
            assert (await c.list_resource_templates()).resource_templates[0].uri_template == "notes://{note_id}"
            one = json.loads((await c.read_resource("notes://1")).contents[0].text)
            assert one["done"] is True

            # prompts
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            assert prompts == {"summarize_notes", "weekly_review"}
            msg = (await c.get_prompt("summarize_notes", {"topic": "work"})).messages[0]
            assert "search_notes" in msg.content.text and "work" in msg.content.text

    run(go())


def test_destructive_hint_is_advertised(tmp_path):
    async def go():
        async with Client(build_server(str(tmp_path / "n.db"))) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert tools["delete_note"].annotations.destructive_hint is True
            assert tools["search_notes"].annotations.read_only_hint is True

    run(go())


def test_real_stdio_subprocess(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(HERE, "mcp_notes_server.py")],
        env={"NOTES_DB": str(tmp_path / "n.db")},
    )

    async def go():
        async with Client(params) as c:
            assert c.server_info.name == "notes"
            r = await c.call_tool("add_note", {"title": "stdio", "body": "works"})
            assert json.loads(r.content[0].text)["title"] == "stdio"

    run(go())


def test_raw_jsonrpc_handshake(tmp_path):
    responses = run_raw(str(tmp_path / "n.db"), verbose=False)
    init, tools_list, call_ok, call_unknown = responses
    assert init["result"]["serverInfo"]["name"] == "notes"
    assert init["result"]["protocolVersion"] == "2025-11-25"
    assert {t["name"] for t in tools_list["result"]["tools"]} >= {"add_note", "search_notes"}
    assert call_ok["result"]["isError"] is False
    assert call_unknown["result"]["isError"] is True
