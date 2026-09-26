"""Generic project runner (labapi/project_lab.py) ke tests. Normal Python mein chalte hain."""
import json

from labapi import run
from labapi.project_lab import build_args, manifest


def collect(req):
    events = []
    out = run(req, events.append)
    json.dumps(events, default=str)
    return out, events


def test_manifest_covers_every_project_with_main():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    mains = {str(p.parent.relative_to(root)) for p in root.glob("**/main.py") if ".venv" not in p.parts}
    assert mains <= set(manifest())


def test_runs_real_main_offline_and_streams_lines():
    out, events = collect({"lab": "project", "params": {"project": "02-agentic-architectures/01-prompt-chaining"}, "offline": True})
    assert out["ok"], out
    r = out["result"]
    assert r["exit_code"] == 0 and r["llm_calls"] >= 1 and r["lines"] > 0
    assert any(e["type"] in ("output", "step") for e in events)
    assert events[0]["type"] == "start" and "--offline" in events[0]["argv"]


def test_values_become_argv():
    info = {"prefix": ["ask"], "inputs": [
        {"name": "q", "kind": "text", "default": "hi"},
        {"name": "tone", "kind": "choice", "arg": "--tone", "default": "friendly"},
        {"name": "nums", "kind": "text", "multi": True, "default": "4 9"},
        {"name": "v", "kind": "flag", "arg": "-v"},
    ]}
    assert build_args(info, {}) == ["ask", "hi", "--tone", "friendly", "4", "9"]
    assert build_args(info, {"q": "yo", "v": True}) == ["ask", "yo", "--tone", "friendly", "4", "9", "-v"]


def test_replay_project_emits_recorded_lines():
    out, events = collect({"lab": "project", "params": {"project": "05-agent-communication/07-mcp/01-mcp-server-stdio"}, "offline": True})
    assert out["ok"] and out["result"]["replay"]
    assert events[0]["type"] == "replay" and len(events) > 5


def test_unknown_project_is_rejected():
    out, _ = collect({"lab": "project", "params": {"project": "../../etc"}, "offline": True})
    assert not out["ok"]


def test_env_and_cwd_are_restored():
    import os

    from agentkit.llm import http

    cwd, before = os.getcwd(), os.environ.get("GROQ_API_KEY")
    http.set_transport(lambda *a: http.HTTPResponse(401, '{"error": "bad key"}'))  # koi asli network nahi
    try:
        collect({"lab": "project", "params": {"project": "04-rag/01-rag-basics"},
                 "llm": {"spec": "groq:x", "keys": {"groq": "secret-key"}}})  # fail hoga, par cleanup hona chahiye
    finally:
        http.set_transport(None)
    assert os.getcwd() == cwd
    assert os.environ.get("GROQ_API_KEY") == before  # user ki key process env mein chhooti nahi
