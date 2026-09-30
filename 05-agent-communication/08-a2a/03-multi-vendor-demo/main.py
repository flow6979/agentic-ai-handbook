"""Multi-vendor A2A demo: 2 alag-alag bane agents + 1 orchestrator.

    python main.py --offline                      # sab in-process, koi key nahi
    python main.py                                # dono servers is process mein real ports (9001, 9002) pe + real LLMs
    python main.py --agents http://127.0.0.1:9001 http://127.0.0.1:9002   # already chal rahe servers use karo
    python main.py --llm-orchestrator "What should I pack for Paris in December for 4 days?"

LLMs (alag providers dikhane ke liye):
    LLM_MODEL_A  -> travel agent ka LLM   (default: LLM_MODEL)
    LLM_MODEL_B  -> orchestrator ka LLM   (default: LLM_MODEL)
    e.g. LLM_MODEL_A=groq:llama-3.3-70b-versatile  LLM_MODEL_B=gemini:gemini-3.8-flash
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))
sys.path.insert(0, os.path.join(HERE, "..", "02-a2a-client-orchestrator"))

from agentkit import get_llm  # noqa: E402

from a2a_orchestrator import AgentRegistry, build_orchestrator_agent, offline_orchestrator_llm  # noqa: E402
from a2a_packing_agent_raw import create_packing_app  # noqa: E402
from a2a_travel_agent import create_app, offline_llm  # noqa: E402
from a2a_trip_planner import TripRequest, plan_trip  # noqa: E402


def serve_in_thread(app, port: int):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default=None)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--agents", nargs="+", default=None)
    ap.add_argument("--llm-orchestrator", action="store_true", help="let an LLM orchestrator pick agents for a free-form question")
    ap.add_argument("--city", default="Tokyo")
    ap.add_argument("--month", type=int, default=1)
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--budget", type=float, default=500)
    ap.add_argument("--home", default="USD")
    ap.add_argument("--local", default="JPY")
    args = ap.parse_args()

    http, servers = None, []
    if args.offline:
        from fastapi.testclient import TestClient

        t = TestClient(create_app(offline_llm(), url="http://travel.local/"), base_url="http://travel.local").__enter__()
        p = TestClient(create_packing_app("http://packing.local/"), base_url="http://packing.local").__enter__()
        http = {"http://travel.local": t, "http://packing.local": p}
        urls = list(http)
        orch_llm, summarizer = offline_orchestrator_llm(), None
    elif args.agents:
        urls = args.agents
        orch_llm = summarizer = get_llm(os.getenv("LLM_MODEL_B"))
    else:
        travel_llm = get_llm(os.getenv("LLM_MODEL_A"))
        servers = [serve_in_thread(create_app(travel_llm, "http://127.0.0.1:9001/"), 9001),
                   serve_in_thread(create_packing_app("http://127.0.0.1:9002/"), 9002)]
        urls = ["http://127.0.0.1:9001", "http://127.0.0.1:9002"]
        orch_llm = summarizer = get_llm(os.getenv("LLM_MODEL_B"))

    try:
        registry = AgentRegistry(urls, http=http)
        for name, a in registry.agents.items():
            c = a.card
            print(f"discovered: {name} by {c.provider.organization if c.provider else '?'} "
                  f"streaming={c.capabilities.streaming} skills={[s.id for s in c.skills]}")
        if args.llm_orchestrator or args.question:
            q = args.question or "What should I pack for Paris in December for 4 days?"
            res = build_orchestrator_agent(orch_llm, registry, ask_human=lambda x: input(f"{x}\n> ")).run(q)
            print("\n=== ANSWER ===\n" + res.output)
        else:
            req = TripRequest(args.city, args.month, args.days, args.budget, args.home, args.local)
            print("\n=== TRIP PLAN ===\n" + plan_trip(registry, req, summarizer=summarizer).render())
    finally:
        for s in servers:
            s.should_exit = True


if __name__ == "__main__":
    main()
