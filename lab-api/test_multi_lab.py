import json

import pytest

from agentkit.llm import http
from labapi import run


def collect(req):
    events = []
    out = run(req, events.append)
    json.dumps(events, default=str)
    json.dumps(out, default=str)
    return out, [e for e in events if e["type"] == "step"], events


def kinds(steps, k):
    return [s for s in steps if s["kind"] == k]


def test_supervisor_offline_routes_and_finishes():
    out, steps, events = collect({"lab": "multi", "params": {"topology": "supervisor"}, "offline": True})
    r = out["result"]
    assert out["ok"] and r["stopped_reason"] == "finish" and "6-10 years" in r["answer"]
    routes = [s["next"] for s in kinds(steps, "route")]
    assert routes == ["researcher", "writer", "critic", "writer", "critic", "FINISH"]
    assert {s["role"] for s in kinds(steps, "agent_active")} == {"supervisor", "researcher", "writer", "critic"}
    assert any(s["sender"] == "researcher" and s["receiver"] == "supervisor" for s in kinds(steps, "message"))
    assert kinds(steps, "tool")[0]["role"] == "researcher"
    roles_in_calls = {e["role"] for e in events if e["type"] == "llm_call"}
    assert "supervisor" in roles_in_calls and r["llm_calls"] >= 6
    assert steps[-1]["kind"] == "done" and steps[-1]["reason"] == "finish"


def test_crew_offline_reworks_once_then_passes():
    out, steps, _ = collect({"lab": "multi", "params": {"topology": "crew"}, "offline": True})
    r = out["result"]
    assert out["ok"] and r["stopped_reason"] == "qa_passed" and r["reworks"] == 1
    assert "TypeError" in r["files"]["calc.py"]
    senders = [(s["sender"], s["receiver"]) for s in kinds(steps, "message")]
    assert ("pm", "architect") in senders and ("qa", "developer") in senders and ("qa", "user") in senders


@pytest.mark.parametrize("selector", ["llm", "rules", "roundrobin"])
def test_groupchat_offline_reaches_consensus(selector):
    out, steps, _ = collect({"lab": "multi", "params": {"topology": "groupchat", "selector": selector}, "offline": True})
    r = out["result"]
    assert out["ok"] and r["rounds"] <= 8
    assert kinds(steps, "message")[0]["sender"] == "user"
    if selector == "llm":
        assert r["stopped_reason"] == "consensus"
        assert "manager" in {s["role"] for s in kinds(steps, "agent_active")}


def test_swarm_offline_hands_off_to_refunds():
    out, steps, _ = collect({"lab": "multi", "params": {"topology": "swarm"}, "offline": True})
    r = out["result"]
    assert out["ok"] and r["path"] == ["triage", "refunds"] and "Refund of INR 2999" in r["answer"]
    h = kinds(steps, "handoff")[0]
    assert (h["sender"], h["receiver"]) == ("triage", "refunds")
    assert kinds(steps, "tool")[0]["role"] == "refunds"


def test_unknown_topology_is_structured_error():
    out, _, _ = collect({"lab": "multi", "params": {"topology": "mesh"}, "offline": True})
    assert not out["ok"] and out["error"]["kind"] == "internal"


def test_per_role_model_spec_reaches_the_provider():
    """params.models[role] -> us role ki calls us provider/model pe jaati hain."""
    seen = []

    def t(method, url, headers, data, timeout):
        body = json.loads(data)
        seen.append((url, body["model"]))
        return http.HTTPResponse(200, json.dumps({"choices": [{"message": {"content": '{"next": "FINISH"}'}, "finish_reason": "stop"}],
                                                  "usage": {"prompt_tokens": 1, "completion_tokens": 1}}))

    http.set_transport(t)
    try:
        out, _, _ = collect({"lab": "multi",
                             "params": {"topology": "supervisor", "models": {"supervisor": "openai:gpt-4o-mini"}},
                             "llm": {"spec": "groq:llama-3.3-70b-versatile", "keys": {"groq": "g", "openai": "o"}}})
        assert out["ok"] and out["result"]["stopped_reason"] == "finish"
        assert seen[0] == ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini")
    finally:
        http.set_transport(None)
