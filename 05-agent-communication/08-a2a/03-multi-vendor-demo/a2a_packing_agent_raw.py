"""'Doosri company' ka agent: hand-written A2A server, bina hamari a2a_protocol/a2a_server_lib ke.

Sirf FastAPI + plain dicts. Koi LLM nahi (rule-based). Fir bhi hamara orchestrator isse
baat kar leta hai, kyunki dono ek hi WIRE CONTRACT (A2A JSON-RPC) bolte hain.
Interoperability ka matlab yahi hai: andar kuch bhi ho, bahar protocol same.

Supports: agent card, message/send (blocking), tasks/get. Streaming NAHI -> card mein
capabilities.streaming=false, isliye achha client isse stream nahi karega.

    python a2a_packing_agent_raw.py --port 9002
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request

CLIMATE = {  # city -> months (1-12) -> climate
    "tokyo": {**{m: "cold" for m in (12, 1, 2)}, **{m: "hot" for m in (6, 7, 8)}},
    "paris": {**{m: "cold" for m in (11, 12, 1, 2)}, **{m: "warm" for m in (6, 7, 8)}},
    "goa": {**{m: "rainy" for m in (6, 7, 8, 9)}, **{m: "hot" for m in (3, 4, 5)}},
    "dubai": {**{m: "hot" for m in range(4, 11)}},
    "london": {**{m: "cold" for m in (11, 12, 1, 2, 3)}},
}
BASE = ["passport", "phone charger", "universal adapter", "medicines"]
BY_CLIMATE = {
    "cold": ["thermal layers", "warm jacket", "gloves"],
    "hot": ["sunscreen", "light cotton clothes", "sunglasses"],
    "rainy": ["umbrella", "quick-dry clothes", "waterproof bag"],
    "warm": ["light jacket", "comfortable walking shoes"],
    "mild": ["light jacket", "comfortable walking shoes"],
}
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
     "November", "December"], start=1)}


def packing_list(city: str, month: int, days: int) -> dict:
    climate = CLIMATE.get(city.lower(), {}).get(month, "mild")
    items = BASE + BY_CLIMATE[climate] + [f"{days} sets of clothes"]
    return {"city": city, "month": month, "days": days, "climate": climate, "items": items}


def parse_request(parts: list[dict]) -> dict:
    """DataPart {city, month, days} ho to wahi; warna text se andaaza."""
    for p in parts:
        if p.get("kind") == "data":
            d = p["data"]
            return {"city": d.get("city", "unknown"), "month": int(d.get("month", 1)), "days": int(d.get("days", 3))}
    text = " ".join(p.get("text", "") for p in parts if p.get("kind") == "text").lower()
    city = next((c for c in CLIMATE if c in text), "unknown")
    month = next((i for name, i in MONTHS.items() if name in text or name[:3] in text.split()), 1)
    days = int(m.group(1)) if (m := re.search(r"(\d+)\s*day", text)) else 3
    return {"city": city, "month": month, "days": days}


def create_packing_app(url: str = "http://127.0.0.1:9002/") -> FastAPI:
    app = FastAPI(title="Packing Assistant")
    tasks: dict[str, dict] = {}
    card = {
        "protocolVersion": "0.2.6",
        "name": "Packing Assistant",
        "description": "Rule-based packing list builder based on destination climate. No LLM inside.",
        "url": url,
        "version": "0.9.0",
        "provider": {"organization": "Another Vendor Inc."},
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [{
            "id": "packing-list", "name": "Packing list",
            "description": "Build a packing list for a trip given city, month and number of days.",
            "tags": ["packing", "pack", "luggage", "clothes", "trip"],
            "examples": ["What should I pack for Tokyo in January for 5 days?"],
        }],
    }

    @app.get("/.well-known/agent.json")
    @app.get("/.well-known/agent-card.json")
    def get_card():
        return card

    def err(req_id, code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    @app.post("/")
    async def rpc(request: Request):
        body = await request.json()
        req_id, method, params = body.get("id"), body.get("method"), body.get("params") or {}
        if method == "message/send":
            msg = params.get("message") or {}
            req = parse_request(msg.get("parts", []))
            result = packing_list(**req)
            text = f"Packing list for {req['city'].title()} ({result['climate']}, {req['days']} days): " + ", ".join(result["items"])
            task_id, ctx_id = str(uuid.uuid4()), msg.get("contextId") or str(uuid.uuid4())
            task = {
                "kind": "task", "id": task_id, "contextId": ctx_id,
                "status": {"state": "completed", "timestamp": datetime.now(timezone.utc).isoformat()},
                "artifacts": [{"artifactId": str(uuid.uuid4()), "name": "packing-list",
                               "parts": [{"kind": "text", "text": text}, {"kind": "data", "data": result}]}],
                "history": [msg],
            }
            tasks[task_id] = task
            return {"jsonrpc": "2.0", "id": req_id, "result": task}
        if method == "tasks/get":
            task = tasks.get(params.get("id"))
            return {"jsonrpc": "2.0", "id": req_id, "result": task} if task else err(req_id, -32001, "Task not found")
        if method == "tasks/cancel":
            return err(req_id, -32002, "Task cannot be canceled") if params.get("id") in tasks else err(req_id, -32001, "Task not found")
        if method == "message/stream":
            return err(req_id, -32004, "Streaming is not supported")
        return err(req_id, -32601, f"Method not found: {method}")

    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9002)
    ap.add_argument("--offline", action="store_true", help="accepted for consistency; this agent never calls an LLM")
    a = ap.parse_args()
    uvicorn.run(create_packing_app(f"http://127.0.0.1:{a.port}/"), host="127.0.0.1", port=a.port, log_level="warning")
