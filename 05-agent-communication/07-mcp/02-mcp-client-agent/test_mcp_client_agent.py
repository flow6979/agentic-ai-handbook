"""Offline tests: in-process MCP servers + ScriptedLLM. Ek test real stdio subprocess bhi."""
import json
import os
import sys

import pytest

from agentkit import Agent, NullTracer, ScriptedLLM, call, tool_response

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-mcp-server-stdio"))

from mcp_bridge import MCPBridge, result_to_text  # noqa: E402
from mcp_client_agent import build_agent, confirm_destructive, default_servers, offline_llm  # noqa: E402
from mcp_notes_server import build_server  # noqa: E402
from mcp_utils_server import build_utils_server  # noqa: E402


@pytest.fixture
def servers(tmp_path):
    return {"notes": build_server(str(tmp_path / "n.db")), "utils": build_utils_server()}


def test_bridge_converts_and_namespaces_tools(servers):
    with MCPBridge(servers) as b:
        tools = {t.name: t for t in b.tools()}
        assert {"notes__add_note", "notes__search_notes", "utils__calculate", "utils__convert_units"} <= set(tools)
        # MCP inputSchema seedha agentkit parameters ban jata hai
        assert tools["notes__add_note"].parameters["required"] == ["title", "body"]
        assert "(DESTRUCTIVE)" in tools["notes__delete_note"].description
        assert b.destructive_tools() == {"notes__delete_note"}
        assert "notes:" in b.instructions() and "utils:" in b.instructions()


def test_agent_calls_tools_across_two_servers(servers):
    llm = ScriptedLLM([
        tool_response(call("notes__add_note", title="Milk", body="2L", tags=["groceries"])),
        tool_response(call("utils__calculate", expression="2*21")),
        "Added the note and 2*21 = 42.",
    ])
    with MCPBridge(servers) as b:
        res = Agent(llm, b.tools(), tracer=NullTracer()).run("add milk and compute 2*21")
        tool_msgs = [m for m in res.messages if m.role == "tool"]
        assert json.loads(tool_msgs[0].content)["title"] == "Milk"
        assert tool_msgs[1].content == "42"
        # note sach mein server ke DB mein gaya?
        assert "Milk" in b.read_resource("notes", "notes://all")


def test_tool_error_reaches_model_as_error_text(servers):
    llm = ScriptedLLM([tool_response(call("notes__mark_done", note_id=99)), "that note does not exist"])
    with MCPBridge(servers) as b:
        res = Agent(llm, b.tools(), tracer=NullTracer()).run("mark 99 done")
        err = [m for m in res.messages if m.role == "tool"][0].content
        assert err.startswith("ERROR:") and "does not exist" in err


def test_allowlist_limits_tools(servers):
    with MCPBridge(servers, allow={"notes__search_notes"}) as b:
        assert [t.name for t in b.tools()] == ["notes__search_notes"]


def test_destructive_tool_needs_human_ok(servers):
    llm = ScriptedLLM([tool_response(call("notes__delete_note", note_id=1)), "ok, not deleted"])
    with MCPBridge(servers) as b:
        approve = confirm_destructive(b, ask=lambda prompt: "n")
        res = build_agent(llm, b, approve=approve, tracer=NullTracer()).run("delete note 1")
        assert "rejected" in [m for m in res.messages if m.role == "tool"][0].content


def test_prompts_and_resources_via_bridge(servers):
    with MCPBridge(servers) as b:
        assert "notes://{note_id}" in b.list_resources("notes")
        assert "open items" in b.get_prompt("notes", "weekly_review")


def test_offline_brain_end_to_end_over_real_stdio(tmp_path):
    """Asli subprocess servers (jaise production host karta hai)."""
    with MCPBridge(default_servers(str(tmp_path / "n.db"))) as b:
        res = build_agent(offline_llm(), b, tracer=NullTracer()).run("add groceries")
        assert "notes__search_notes" in res.output and "Groceries" in res.output


def test_result_to_text_handles_structured_only():
    class R:
        content = []
        structured_content = {"a": 1}
        is_error = False

    assert result_to_text(R()) == '{"a": 1}'


def test_bad_server_name_rejected():
    with pytest.raises(ValueError):
        with MCPBridge({"bad__name": build_utils_server()}):
            pass
