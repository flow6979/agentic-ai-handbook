import json

from agentkit.llm import http
from labapi import catalog, run


def collect(req):
    events = []
    out = run(req, events.append)
    json.dumps(events, default=str)  # UI tak jaane ke liye sab JSON-safe hona chahiye
    json.dumps(out, default=str)
    return out, events


def test_catalog_discovers_labs():
    ids = {l["id"] for l in catalog()}
    assert {"ping", "react"} <= ids


def test_ping_offline():
    out, events = collect({"lab": "ping", "offline": True})
    assert out["ok"] and out["result"]["ok"] and out["result"]["llm_calls"] == 1
    assert events[0]["type"] == "llm_call"


def test_react_text_offline_streams_steps():
    out, events = collect({"lab": "react", "params": {"mode": "text"}, "offline": True})
    r = out["result"]
    assert out["ok"] and "26.8" in r["answer"] and r["llm_calls"] == 4
    kinds = [e["kind"] for e in events if e["type"] == "step"]
    assert kinds[:3] == ["thought", "action", "observation"] and kinds[-1] == "answer"


def test_react_native_offline():
    out, events = collect({"lab": "react", "params": {"mode": "native"}, "offline": True})
    kinds = [e["kind"] for e in events if e["type"] == "step"]
    assert out["ok"] and kinds.count("tool_call") == 3 and kinds[-1] == "answer"
    assert out["result"]["llm_calls"] == 3


def test_react_max_steps_tinker():
    out, events = collect({"lab": "react", "params": {"mode": "native", "max_steps": 1}, "offline": True})
    assert out["result"]["stopped_reason"] == "max_steps"


def test_react_lookup_fails_first_is_observed():
    out, events = collect({"lab": "react", "params": {"mode": "native", "lookup_fails_first": True}, "offline": True})
    results = [e for e in events if e.get("kind") == "tool_result"]
    assert results[0]["error"] and "TimeoutError" in results[0]["text"]


def fake_transport(status, body):
    seen = {}

    def t(method, url, headers, data, timeout):
        seen.update(url=url, headers=headers, body=json.loads(data))
        return http.HTTPResponse(status, json.dumps(body))
    return t, seen


def test_real_path_uses_user_key_and_classifies_errors():
    ok = {"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
          "usage": {"prompt_tokens": 7, "completion_tokens": 1}, "model": "llama-3.3-70b-versatile"}
    t, seen = fake_transport(200, ok)
    http.set_transport(t)
    try:
        out, _ = collect({"lab": "ping", "llm": {"spec": "groq:llama-3.3-70b-versatile", "keys": {"groq": "gsk_test"}}})
        assert out["ok"] and out["result"]["ok"]
        assert seen["headers"]["Authorization"] == "Bearer gsk_test"
        assert seen["url"].startswith("https://api.groq.com")

        t401, _ = fake_transport(401, {"error": "bad key"})
        http.set_transport(t401)
        out, events = collect({"lab": "ping", "llm": {"spec": "groq:llama-3.3-70b-versatile", "keys": {"groq": "bad"}}})
        assert not out["ok"] and out["error"]["kind"] == "auth" and out["error"]["status"] == 401
        assert events[-1]["type"] == "error"

        t429, _ = fake_transport(429, {"error": "slow down"})
        http.set_transport(t429)
        out, _ = collect({"lab": "ping", "llm": {"spec": "groq:x", "keys": {"groq": "k"}}})
        assert out["error"]["kind"] == "rate_limit"
    finally:
        http.set_transport(None)


def test_missing_key_is_auth_error():
    out, _ = collect({"lab": "ping", "llm": {"spec": "gemini:gemini-3.8-flash", "keys": {}}})
    assert out["error"]["kind"] == "auth"
