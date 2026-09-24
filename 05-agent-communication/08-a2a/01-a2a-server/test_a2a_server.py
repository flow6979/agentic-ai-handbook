"""Raw JSON-RPC tests (koi client library nahi) taaki wire format saaf dikhe."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from agentkit import LLMResponse, ScriptedLLM, ToolCall

from a2a_protocol import parse_event
from a2a_server_lib import build_a2a_app
from a2a_travel_agent import create_app, make_card, offline_llm


def msg(text, task_id=None, **extra):
    m = {"kind": "message", "role": "user", "messageId": f"m-{time.time_ns()}", "parts": [{"kind": "text", "text": text}]}
    if task_id:
        m["taskId"] = task_id
    m.update(extra)
    return m


def rpc(client, method, params, req_id=1):
    r = client.post("/", json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def client():
    with TestClient(create_app(offline_llm())) as c:
        yield c


def test_agent_card_on_both_paths(client):
    for path in ("/.well-known/agent.json", "/.well-known/agent-card.json"):
        card = client.get(path).json()
        assert card["name"] == "Travel & Currency Expert"
        assert card["capabilities"]["streaming"] is True
        assert {s["id"] for s in card["skills"]} == {"currency-conversion", "travel-tips"}
        assert "defaultInputModes" in card  # camelCase on the wire


def test_message_send_completes_with_artifact_and_data_part(client):
    res = rpc(client, "message/send", {"message": msg("convert 100 USD to INR")})["result"]
    assert res["kind"] == "task" and res["status"]["state"] == "completed"
    parts = res["artifacts"][0]["parts"]
    assert "8300.0 INR" in parts[0]["text"]
    assert parts[1] == {"kind": "data", "data": {"conversions": [
        {"amount": 100.0, "from": "USD", "to": "INR", "rate": 83.0, "converted": 8300.0}]}}
    roles = [m["role"] for m in res["history"]]
    assert roles[0] == "user" and "agent" in roles


def test_input_required_multi_turn(client):
    first = rpc(client, "message/send", {"message": msg("convert 50 EUR")})["result"]
    assert first["status"]["state"] == "input-required"
    assert "Which currency" in first["status"]["message"]["parts"][0]["text"]
    # same taskId pe jawab
    second = rpc(client, "message/send", {"message": msg("to GBP", task_id=first["id"])})["result"]
    assert second["id"] == first["id"] and second["status"]["state"] == "completed"
    assert "GBP" in second["artifacts"][0]["parts"][0]["text"]
    # completed task ko dobara message -> error
    err = rpc(client, "message/send", {"message": msg("again", task_id=first["id"])})["error"]
    assert err["code"] == -32004


def test_tasks_get_history_length_and_not_found(client):
    task = rpc(client, "message/send", {"message": msg("tips for tokyo")})["result"]
    got = rpc(client, "tasks/get", {"id": task["id"], "historyLength": 1})["result"]
    assert got["status"]["state"] == "completed" and len(got["history"]) == 1
    assert rpc(client, "tasks/get", {"id": "nope"})["error"]["code"] == -32001


def test_cancel_rules(client):
    t = rpc(client, "message/send", {"message": msg("convert 10 USD")})["result"]  # input-required = cancelable
    assert rpc(client, "tasks/cancel", {"id": t["id"]})["result"]["status"]["state"] == "canceled"
    assert rpc(client, "tasks/cancel", {"id": t["id"]})["error"]["code"] == -32002  # already terminal


def test_streaming_sse_events(client):
    body = {"jsonrpc": "2.0", "id": 7, "method": "message/stream", "params": {"message": msg("convert 1 GBP to JPY")}}
    events = []
    with client.stream("POST", "/", json=body) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                frame = json.loads(line[6:])
                assert frame["id"] == 7
                events.append(parse_event(frame["result"]))
    kinds = [e.kind for e in events]
    assert kinds[0] == "task" and "artifact-update" in kinds
    working_notes = [e.status.message.text() for e in events if e.kind == "status-update" and e.status.message]
    assert any("convert_currency" in n for n in working_notes)  # tool call streamed live
    assert events[-1].kind == "status-update" and events[-1].final and events[-1].status.state.value == "completed"


def test_non_blocking_send_then_poll(client):
    res = rpc(client, "message/send", {"message": msg("tips for paris"), "configuration": {"blocking": False}})["result"]
    assert res["status"]["state"] in ("working", "submitted", "completed")
    for _ in range(100):
        got = rpc(client, "tasks/get", {"id": res["id"]})["result"]
        if got["status"]["state"] == "completed":
            break
        time.sleep(0.02)
    assert got["status"]["state"] == "completed" and "Navigo" in got["artifacts"][0]["parts"][0]["text"]


def test_jsonrpc_error_codes(client):
    assert client.post("/", content=b"{not json").json()["error"]["code"] == -32700
    assert client.post("/", json={"id": 1, "method": "x"}).json()["error"]["code"] == -32600
    assert rpc(client, "does/not/exist", {})["error"]["code"] == -32601
    assert rpc(client, "message/send", {"message": {"role": "user"}})["error"]["code"] == -32602
    assert rpc(client, "tasks/pushNotificationConfig/set", {})["error"]["code"] == -32003


def test_executor_crash_becomes_failed_task():
    def broken(messages, tools):
        raise RuntimeError("LLM exploded")

    with TestClient(create_app(ScriptedLLM(broken))) as c:
        res = rpc(c, "message/send", {"message": msg("hello")})["result"]
        assert res["status"]["state"] == "failed"
        assert "LLM exploded" in res["status"]["message"]["parts"][0]["text"]


def test_bearer_auth_enforced_and_declared_in_card():
    with TestClient(create_app(offline_llm(), token="s3cret")) as c:
        assert c.get("/.well-known/agent.json").json()["securitySchemes"]["bearer"]["scheme"] == "bearer"
        assert c.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}}).status_code == 401
        ok = c.post("/", headers={"Authorization": "Bearer s3cret"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}})
        assert ok.json()["error"]["code"] == -32001


def test_generic_lib_with_plain_function_executor():
    """build_a2a_app kisi bhi executor ke saath chalta hai - LLM zaroori nahi."""
    async def echo(ctx):
        yield ctx.status("completed", f"echo: {ctx.message.text()}", final=True)

    with TestClient(build_a2a_app(make_card("http://x/"), echo)) as c:
        res = rpc(c, "message/send", {"message": msg("hi")})["result"]
        assert res["status"]["message"]["parts"][0]["text"] == "echo: hi"


def test_llm_tool_call_path_with_scripted_llm():
    llm = ScriptedLLM([LLMResponse(None, [ToolCall("1", "travel_tips", {"city": "Goa"})]), "Goa tips delivered."])
    with TestClient(create_app(llm)) as c:
        res = rpc(c, "message/send", {"message": msg("going to goa")})["result"]
        assert res["artifacts"][0]["parts"][0]["text"] == "Goa tips delivered."
