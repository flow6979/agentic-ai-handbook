"""Agents as HTTP microservices.

Offline (sab in-process, koi port nahi):
    python 05-agent-communication/06-http-agent-services/main.py --offline

Real (4 terminals, repo root se):
    T1: python 05-agent-communication/06-http-agent-services/main.py serve registry   --port 8000
    T2: python 05-agent-communication/06-http-agent-services/main.py serve summarizer --port 8001
    T3: python 05-agent-communication/06-http-agent-services/main.py serve sentiment  --port 8002
    T4: python 05-agent-communication/06-http-agent-services/main.py ask "Review: The phone is fast but the battery dies by noon."
        python 05-agent-communication/06-http-agent-services/main.py job summarizer "long text..."
"""
from __future__ import annotations

import argparse
import os

from agentkit import ScriptedLLM, call, get_llm, tool_response

from httpsvc_agents import SERVICES, build_orchestrator, make_skill
from httpsvc_client import AgentClient
from httpsvc_registry import create_registry_app
from httpsvc_service import create_agent_app

TOKEN = os.getenv("AGENT_SERVICE_TOKEN", "dev-secret")
REVIEW = "The phone is super fast and the screen is gorgeous, but the battery dies by noon."


def serve(which: str, port: int, registry: str) -> None:
    import uvicorn

    if which == "registry":
        app = create_registry_app(TOKEN)
    else:
        skills, _ = SERVICES[which]
        app = create_agent_app(which, skills, make_skill(get_llm(), which), token=TOKEN,
                               register_with=registry, public_url=f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)


def offline_demo() -> None:
    from fastapi.testclient import TestClient

    def skill_llm(messages, tools):
        system = messages[0].content or ""
        return "Fast phone, great screen, weak battery." if "Summarize" in system else "mixed: loves speed, hates battery"

    skill = ScriptedLLM(skill_llm)
    apps = {
        "http://registry": create_registry_app(TOKEN),
        "http://summarizer": create_agent_app("summarizer", ["summarize"], make_skill(skill, "summarizer"), token=TOKEN),
        "http://sentiment": create_agent_app("sentiment", ["sentiment"], make_skill(skill, "sentiment"), token=TOKEN),
    }
    clients = {base: TestClient(app, base_url=base) for base, app in apps.items()}
    reg = clients["http://registry"]
    for name in ("summarizer", "sentiment"):  # real mein lifespan khud register karta hai
        reg.post("/register", json={"name": name, "url": f"http://{name}", "skills": SERVICES[name][0]},
                 headers={"Authorization": f"Bearer {TOKEN}"})

    client = AgentClient("http://registry", TOKEN, http_factory=lambda base: clients[base])
    orch_llm = ScriptedLLM([
        tool_response(call("list_remote_skills")),
        tool_response(call("call_remote_agent", skill="summarize", text=REVIEW),
                      call("call_remote_agent", skill="sentiment", text=REVIEW)),
        "Summary: fast phone, great screen, weak battery. Sentiment: mixed.",
    ])
    print("=== SYNC (orchestrator -> registry -> agents) ===")
    print(build_orchestrator(orch_llm, client).run(f"Summarize and get sentiment of: {REVIEW}").output)

    print("\n=== ASYNC JOB (submit -> poll) ===")
    job_id = client.submit_job("http://summarizer", REVIEW)
    print("submitted", job_id, "->", client.wait_for_job("http://summarizer", job_id, poll_every=0.01))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("which", choices=["registry", *SERVICES])
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--registry", default="http://127.0.0.1:8000")
    a = sub.add_parser("ask")
    a.add_argument("text")
    a.add_argument("--registry", default="http://127.0.0.1:8000")
    j = sub.add_parser("job")
    j.add_argument("which", choices=list(SERVICES))
    j.add_argument("text")
    j.add_argument("--registry", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    if args.offline or args.cmd is None:
        offline_demo()
    elif args.cmd == "serve":
        serve(args.which, args.port, args.registry)
    elif args.cmd == "ask":
        client = AgentClient(args.registry, TOKEN)
        print(build_orchestrator(get_llm(), client).run(args.text).output)
    elif args.cmd == "job":
        client = AgentClient(args.registry, TOKEN)
        url = client.discover(SERVICES[args.which][0][0])[0]["url"]
        job_id = client.submit_job(url, args.text)
        print("job", job_id, "submitted; polling...")
        print(client.wait_for_job(url, job_id))


if __name__ == "__main__":
    main()
