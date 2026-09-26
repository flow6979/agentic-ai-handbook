"""Communication lab (MCP + A2A): REPLAY of a real local run.

MCP stdio servers aur A2A FastAPI servers browser (Pyodide) mein nahi chal sakte: na subprocess, na
sockets. Isliye `lab-api/record_comm_traces.py` local machine pe ASLI handbook code chalata hai
(mcp_notes_server.py + travel A2A agent + orchestrator) aur har JSON-RPC / HTTP / SSE message
`data/comm_traces.json` mein record karta hai. Yeh lab wahi messages ek-ek karke UI ko bhejta hai.

params:
    protocol: "mcp" | "a2a"

UI events (type="step", kind="message"): from, to, msg_kind, method, text (=label), json, t_ms, seq, state
"""
from __future__ import annotations

import json
from pathlib import Path

from .registry import Lab
from .runtime import LabContext

DATA = Path(__file__).resolve().parent / "data" / "comm_traces.json"
PROJECTS = {"mcp": "05-agent-communication/07-mcp", "a2a": "05-agent-communication/08-a2a"}


def load_traces() -> dict:
    return json.loads(DATA.read_text())


def run(ctx: LabContext) -> dict:
    protocol = ctx.params.get("protocol", "mcp")
    if protocol not in PROJECTS:
        raise ValueError(f"protocol must be one of {sorted(PROJECTS)}, got {protocol!r}")
    data = load_traces()
    trace = data[protocol]
    meta = {"recorded_at": data["recorded_at"], "command": data["command"], "mcp_sdk": data.get("mcp_sdk"),
            "python": data.get("python"), "project": PROJECTS[protocol]}
    ctx.emit({"type": "replay", "protocol": protocol, **meta, "lanes": trace["lanes"]})
    for m in trace["messages"]:
        extra = {k: v for k, v in m.items() if k not in ("label", "kind")}
        ctx.step("message", m["label"], protocol=protocol, msg_kind=m["kind"], **extra)
    answer = next((m["json"] for m in reversed(trace["messages"]) if m["kind"] == "answer"), "")
    return {"protocol": protocol, "replay": True, "lanes": trace["lanes"], "question": trace["question"],
            "answer": answer, "count": len(trace["messages"]), "messages": trace["messages"], **meta,
            "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "ms": 0}


LAB = Lab(id="comm", project="05-agent-communication", run=run, live=False,
          defaults={"protocol": "mcp"},
          smoke_cases=[{"protocol": "mcp"}, {"protocol": "a2a"}])
