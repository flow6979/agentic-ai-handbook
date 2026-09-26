import json

from labapi import catalog, run
from labapi.comm_lab import load_traces


def collect(req):
    events = []
    out = run(req, events.append)
    json.dumps(events)
    return out, events


def test_comm_lab_is_registered_as_replay():
    lab = next(l for l in catalog() if l["id"] == "comm")
    assert lab["live"] is False


def test_recorded_traces_have_real_protocol_messages():
    d = load_traces()
    assert d["recorded_at"] and d["command"].endswith("record_comm_traces.py")
    mcp_methods = [m["method"] for m in d["mcp"]["messages"] if m["kind"] == "request"]
    assert mcp_methods[:2] == ["initialize", "tools/list"] and "tools/call" in mcp_methods
    init = next(m for m in d["mcp"]["messages"] if m["kind"] == "response" and m["method"] == "initialize")
    assert init["json"]["jsonrpc"] == "2.0" and "serverInfo" in init["json"]["result"]
    states = [m.get("state") for m in d["a2a"]["messages"] if m.get("state")]
    assert "input-required" in states and "completed" in states and "submitted" in states
    assert any(m["kind"] == "sse" for m in d["a2a"]["messages"])


def test_replay_streams_every_message():
    for proto in ("mcp", "a2a"):
        out, events = collect({"lab": "comm", "params": {"protocol": proto}})
        assert out["ok"] and out["result"]["replay"] is True
        assert events[0]["type"] == "replay" and events[0]["recorded_at"]
        steps = [e for e in events if e["type"] == "step"]
        assert len(steps) == out["result"]["count"] and steps[0]["seq"] == 1
        assert out["result"]["answer"]


def test_bad_protocol_is_an_error():
    out, _ = collect({"lab": "comm", "params": {"protocol": "smtp"}})
    assert not out["ok"]
