"""A2A client/orchestrator demo.

Terminal 1:  python ../01-a2a-server/main.py            (ya --offline)
Terminal 2:  python main.py "convert 250 USD"             # LLM orchestrator; agent 'which currency?' poochhega -> tum type karo
             python main.py --mode router "tips for Tokyo"   # bina LLM ke skill routing
             python main.py --mode stream "convert 10 GBP to JPY"   # live SSE events
             python main.py --mode poll "tips for paris"     # non-blocking send + tasks/get polling
             python main.py --offline "convert 250 USD"      # sab kuch in-process: remote agent + fake LLMs, answers scripted
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))

from agentkit import get_llm  # noqa: E402

from a2a_client import task_answer  # noqa: E402
from a2a_orchestrator import (AgentRegistry, SkillRouter, build_orchestrator_agent, delegate,  # noqa: E402
                              delegate_streaming, offline_orchestrator_llm)

OFFLINE_URL = "http://testserver"


def print_event(ev) -> None:
    if ev.kind == "task":
        print(f"  [task] {ev.id[:8]} state={ev.status.state.value}")
    elif ev.kind == "status-update":
        note = ev.status.message.text() if ev.status.message else ""
        print(f"  [status] {ev.status.state.value}{' (final)' if ev.final else ''} {note}")
    elif ev.kind == "artifact-update":
        print(f"  [artifact] {ev.artifact.name}: {[p.kind for p in ev.artifact.parts]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="convert 250 USD")
    ap.add_argument("--agents", nargs="+", default=["http://127.0.0.1:9001"])
    ap.add_argument("--mode", choices=["llm", "router", "stream", "poll"], default="llm")
    ap.add_argument("--token", default=None)
    ap.add_argument("--offline", action="store_true", help="in-process remote agent + scripted LLMs + scripted human")
    args = ap.parse_args()

    http = None
    ask_human = lambda q: input(f"{q}\n> ")  # noqa: E731
    if args.offline:
        from fastapi.testclient import TestClient

        from a2a_travel_agent import create_app, offline_llm

        tc = TestClient(create_app(offline_llm(), url=OFFLINE_URL + "/")).__enter__()
        http, args.agents = {OFFLINE_URL: tc}, [OFFLINE_URL]
        ask_human = lambda q: (print(f"{q}\n> INR (scripted human)") or "INR")  # noqa: E731

    registry = AgentRegistry(args.agents, http=http, token=args.token)
    print("Discovered:", ", ".join(f"{n} {[s.id for s in a.card.skills]}" for n, a in registry.agents.items()))

    if args.mode == "router":
        name, skill = SkillRouter(registry).pick(args.task)
        print(f"router picked {name} / {skill}")
        print("\n=== ANSWER ===\n" + task_answer(delegate(registry.get(name), args.task, ask_human=ask_human)))
    elif args.mode == "stream":
        name, _ = SkillRouter(registry).pick(args.task)
        final = delegate_streaming(registry.get(name), args.task, print_event)
        print("\n=== ANSWER ===\n" + (task_answer(final) if final else "(no task)"))
    elif args.mode == "poll":
        name, _ = SkillRouter(registry).pick(args.task)
        client = registry.get(name).client
        t = client.send(args.task, blocking=False)
        print(f"submitted {t.id[:8]} state={t.status.state.value}; polling tasks/get ...")
        print("\n=== ANSWER ===\n" + task_answer(client.wait(t.id)))
    else:
        llm = offline_orchestrator_llm() if args.offline else get_llm()
        result = build_orchestrator_agent(llm, registry, ask_human=ask_human).run(args.task)
        print("\n=== ANSWER ===\n" + result.output)


if __name__ == "__main__":
    main()
