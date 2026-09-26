"""Record REAL MCP + A2A message traces for the agent-lab website's Communication lab.

Browser (Pyodide) mein MCP stdio subprocess ya FastAPI server nahi chal sakta. Isliye hum yahan
LOCAL machine pe asli handbook code chalate hain aur har message record karte hain:

  MCP : real `mcp_notes_server.py` stdio subprocess (mcp SDK 2.x MCPServer) + raw JSON-RPC client
        + agentkit Agent (ScriptedLLM) as the host. Har stdin/stdout line jaisi thi waisi record hoti hai.
  A2A : real travel agent FastAPI app (a2a_server_lib) via in-process httpx TestClient
        + real A2AClient / AgentRegistry / orchestrator Agent (ScriptedLLM). Har HTTP request/response
        aur SSE event record hota hai.

Output: lab-api/labapi/data/comm_traces.json  (labapi/comm_lab.py isse replay karta hai)

    .venv/bin/python lab-api/record_comm_traces.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "05-agent-communication/07-mcp/01-mcp-server-stdio"
A2A_SERVER = ROOT / "05-agent-communication/08-a2a/01-a2a-server"
A2A_CLIENT = ROOT / "05-agent-communication/08-a2a/02-a2a-client-orchestrator"
OUT = Path(__file__).resolve().parent / "labapi/data/comm_traces.json"
COMMAND = ".venv/bin/python lab-api/record_comm_traces.py"


class Recorder:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.msgs: list[dict] = []

    def add(self, frm: str, to: str, kind: str, label: str, payload, *, method: str | None = None, **extra) -> None:
        self.msgs.append({
            "seq": len(self.msgs) + 1,
            "t_ms": round((time.perf_counter() - self.t0) * 1000, 1),
            "from": frm, "to": to, "kind": kind, "method": method, "label": label,
            "json": payload, **extra,
        })


# ─────────────────────────────────────────────── MCP ──
def record_mcp() -> dict:
    sys.path.insert(0, str(ROOT / "common"))
    from agentkit import Agent, NullTracer, ScriptedLLM, Tool, call, tool_response

    rec = Recorder()
    PROTOCOL = "2025-11-25"
    with tempfile.TemporaryDirectory() as d:
        rec.add("host", "client", "note", "spawn stdio subprocess: python mcp_notes_server.py",
                {"transport": "stdio", "command": [os.path.basename(sys.executable), "mcp_notes_server.py"]})
        proc = subprocess.Popen([sys.executable, str(MCP_DIR / "mcp_notes_server.py")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                env={**os.environ, "NOTES_DB": os.path.join(d, "notes.sqlite3")})
        ids = iter(range(1, 100))

        def send(method: str, params: dict | None = None, *, notify: bool = False) -> dict | None:
            msg: dict = {"jsonrpc": "2.0", "method": method}
            if not notify:
                msg["id"] = next(ids)
            if params is not None:
                msg["params"] = params
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            rec.add("client", "server", "notification" if notify else "request", method, msg, method=method)
            if notify:
                return None
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("server closed stdout")
                resp = json.loads(line)
                if resp.get("id") == msg["id"]:
                    ok = "error" not in resp and not (resp.get("result") or {}).get("isError")
                    rec.add("server", "client", "response", f"result: {method}" if ok else f"error: {method}", resp,
                            method=method, error=not ok)
                    return resp

        try:
            send("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                "clientInfo": {"name": "agent-lab-recorder", "version": "0.1"}})
            send("notifications/initialized", notify=True)
            tools_resp = send("tools/list")
            send("resources/list")
            send("prompts/list")

            def mcp_tool(t: dict) -> Tool:
                def fn(**kw):
                    resp = send("tools/call", {"name": t["name"], "arguments": kw})
                    res = resp.get("result", {})
                    text = "\n".join(c.get("text", "") for c in res.get("content", []))
                    return f"ERROR: {text}" if res.get("isError") else text
                return Tool(t["name"], t.get("description") or t["name"], t["inputSchema"], fn)

            tools = [mcp_tool(t) for t in tools_resp["result"]["tools"]]
            rec.add("client", "host", "note", f"{len(tools)} MCP tools -> agentkit Tools",
                    {"tools": [t.name for t in tools]})

            question = "Add a note to buy 2L milk (tag groceries), then show my grocery notes."
            llm = ScriptedLLM([
                tool_response(call("add_note", title="Buy milk", body="2L toned milk", tags=["groceries"])),
                tool_response(call("search_notes", query="milk")),
                "Done: I added 'Buy milk' (tag groceries). Your grocery notes: Buy milk (2L toned milk).",
            ])

            class HostTracer(NullTracer):
                def event(self, kind, message, **data):
                    super().event(kind, message, **data)
                    if kind == "tool":
                        rec.add("host", "client", "llm", f"LLM chose tool: {message}", {"tool_call": message})
                    elif kind == "llm" and message.startswith("-> "):
                        rec.add("client", "host", "tool_result", "tool result back to LLM", message[3:])

            rec.add("host", "host", "llm", f"user: {question}", {"role": "user", "content": question})
            res = Agent(llm, tools, name="host", tracer=HostTracer(name="host")).run(question)
            rec.add("host", "host", "answer", "final answer", res.output)
        finally:
            proc.stdin.close()
            proc.wait(timeout=10)
    return {"lanes": ["host", "client", "server"], "question": question, "messages": rec.msgs}


# ─────────────────────────────────────────────── A2A ──
def record_a2a() -> dict:
    for p in (ROOT / "common", A2A_SERVER, A2A_CLIENT):
        sys.path.insert(0, str(p))
    from fastapi.testclient import TestClient

    from agentkit import LLM, NullTracer
    from a2a_orchestrator import AgentRegistry, build_orchestrator_agent, delegate_streaming, offline_orchestrator_llm
    from a2a_travel_agent import create_app, offline_llm

    rec = Recorder()
    URL = "http://travel.local"

    class RemoteBrain(LLM):
        """Remote agent ka andar ka LLM: record karo taaki UI dikha sake ki yeh orchestrator ko NAHI dikhta."""
        provider, model = "scripted", "travel-offline"

        def __init__(self, inner):
            self.inner = inner

        def chat(self, messages, tools=None, **kw):
            r = self.inner.chat(messages, tools, **kw)
            for c in r.tool_calls:
                rec.add("remote", "remote", "internal", f"inside remote agent: {c.name}({c.arguments})",
                        {"tool_call": {"name": c.name, "arguments": c.arguments}})
            return r

    def on_request(req):
        body = None
        if req.content:
            try:
                body = json.loads(req.content)
            except ValueError:
                body = req.content.decode(errors="replace")
        method = body.get("method") if isinstance(body, dict) else None
        label = method or f"{req.method} {req.url.path}"
        rec.add("orchestrator", "remote", "request", label,
                {"http": f"{req.method} {req.url.path}", "body": body}, method=method or "agent-card")

    def on_response(resp):
        req = resp.request
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            rec.add("remote", "orchestrator", "response", "200 text/event-stream (SSE opens)",
                    {"http": f"{resp.status_code} text/event-stream"}, method="message/stream")
            return
        resp.read()
        data = resp.json()
        method = None
        if req.content:
            try:
                method = json.loads(req.content).get("method")
            except ValueError:
                pass
        result = data.get("result") if isinstance(data, dict) else None
        state = (result or {}).get("status", {}).get("state") if isinstance(result, dict) else None
        if method:
            label = f"result: {method}" + (f" (state={state})" if state else "")
        else:
            label = f"agent card: {data.get('name')}"
        rec.add("remote", "orchestrator", "response", label, data, method=method or "agent-card", state=state)

    app = create_app(RemoteBrain(offline_llm()), url=URL + "/")
    with TestClient(app, base_url=URL) as http:
        http.event_hooks = {"request": [on_request], "response": [on_response]}
        rec.add("orchestrator", "remote", "note", "discovery: fetch the Agent Card", {"url": URL + "/.well-known/agent.json"})
        registry = AgentRegistry([URL], http={URL: http})

        question = "convert 20 USD"

        def ask_human(q: str) -> str:
            rec.add("orchestrator", "user", "input_required", f"ask user: {q}", {"question": q})
            rec.add("user", "orchestrator", "human", "user answers: INR", {"answer": "INR"})
            return "INR"

        class OrchTracer(NullTracer):
            def event(self, kind, message, **data):
                super().event(kind, message, **data)
                if kind == "tool" and not message.startswith("ask_user"):
                    rec.add("orchestrator", "orchestrator", "llm", f"orchestrator LLM chose: {message}", {"tool_call": message})

        rec.add("user", "orchestrator", "human", f"user: {question}", {"content": question})
        res = build_orchestrator_agent(offline_orchestrator_llm(), registry, ask_human=ask_human,
                                       tracer=OrchTracer(name="orchestrator")).run(question)
        rec.add("orchestrator", "user", "answer", "final answer", res.output)

        stream_q = "tips for london"
        rec.add("user", "orchestrator", "human", f"user: {stream_q} (streaming)", {"content": stream_q})

        def on_event(ev):
            wire = ev.wire()
            state = wire.get("status", {}).get("state") if isinstance(wire, dict) else None
            kind = wire.get("kind")
            label = f"SSE {kind}" + (f" (state={state})" if state else "")
            rec.add("remote", "orchestrator", "sse", label, wire, method="message/stream", state=state)

        final = delegate_streaming(registry.get("Travel & Currency Expert"), stream_q, on_event)
        from a2a_client import task_answer
        rec.add("orchestrator", "user", "answer", "final answer (streamed)", task_answer(final) if final else "")
    return {"lanes": ["user", "orchestrator", "remote"], "question": question, "messages": rec.msgs}


def main() -> None:
    import mcp

    data = {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": COMMAND,
        "mcp_sdk": getattr(mcp, "__version__", None) or _pkg_version("mcp"),
        "python": sys.version.split()[0],
        "mcp": record_mcp(),
        "a2a": record_a2a(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: mcp={len(data['mcp']['messages'])} a2a={len(data['a2a']['messages'])} messages")


def _pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


if __name__ == "__main__":
    main()
