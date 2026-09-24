"""Human-in-the-loop demo (DevOps on-call assistant).

Interactive (same process, terminal mein approve karo):
    python 02-agentic-architectures/11-human-in-the-loop/main.py "checkout service is slow, investigate and fix it"

Async (process ruk ke exit, baad mein resume: jaise Slack approval):
    python 02-agentic-architectures/11-human-in-the-loop/main.py --async "checkout is slow, fix it"
    python 02-agentic-architectures/11-human-in-the-loop/main.py --resume 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json --decision approve
    python 02-agentic-architectures/11-human-in-the-loop/main.py --resume 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json --decision edit --args '{"replicas": 4}'
    python 02-agentic-architectures/11-human-in-the-loop/main.py --resume 02-agentic-architectures/11-human-in-the-loop/.hitl_runs/<id>.json --decision reject --note "not during peak"

Offline (scripted LLM + scripted human):
    python 02-agentic-architectures/11-human-in-the-loop/main.py --offline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentkit import ScriptedLLM, Tracer, call, get_llm, tool_response

from hitl_agent import Decision, HITLAgent, RunState
from hitl_tools import POLICY, TOOLS

CKPT_DIR = Path(__file__).parent / ".hitl_runs"  # project folder ke andar (gitignored)


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM([
        tool_response(call("get_service_status", service="checkout"), call("read_logs", service="checkout")),
        tool_response(call("scale_service", service="checkout", replicas=10),
                      text="DB pool is exhausted and queue is long. I'll add capacity."),
        tool_response(call("restart_service", service="checkout")),
        tool_response(call("delete_database", database="checkout_cache"), text="Cache may be corrupt, deleting it."),
        "Checkout was degraded (DB pool exhausted). Scaled to 4 replicas (human-edited from 10) and restarted it; "
        "it is healthy now. Deleting checkout_cache is not allowed for me, so I escalated it as ESC-1.",
    ])


OFFLINE_HUMAN = [Decision("edit", {"replicas": 4}, note="10 is too many, max 4"), Decision("approve")]


def ask_human(state: RunState) -> Decision:
    c = state.awaiting
    print(f"\n>>> APPROVAL NEEDED: {c.name}({json.dumps(c.arguments)})")
    while True:
        choice = input("[a]pprove / [e]dit args / [r]eject ? ").strip().lower()
        if choice == "a":
            return Decision("approve")
        if choice == "r":
            return Decision("reject", note=input("reason: "))
        if choice == "e":
            try:
                return Decision("edit", json.loads(input('new args as JSON, e.g. {"replicas": 4}: ')))
            except json.JSONDecodeError:
                print("invalid JSON, try again")


def print_final(state: RunState) -> None:
    print(f"\nSTATUS: {state.status}")
    if state.output:
        print(f"ANSWER: {state.output}")
    if state.escalations:
        print(f"ESCALATIONS: {state.escalations}")
    if state.audit:
        print("AUDIT LOG:")
        for a in state.audit:
            print(f"  - {a['reviewer']} {a['action']} {a['tool']} {a['args']} edited={a['edited_args']} note={a['note']!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="checkout service is slow, investigate and fix it")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--async", dest="async_mode", action="store_true", help="exit when approval is needed")
    ap.add_argument("--resume", help="checkpoint JSON to resume")
    ap.add_argument("--decision", choices=["approve", "reject", "edit"])
    ap.add_argument("--args", help="JSON args for --decision edit")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    llm = offline_llm() if a.offline else get_llm()
    agent = HITLAgent(llm, TOOLS, POLICY, checkpoint_dir=CKPT_DIR, tracer=Tracer(name="hitl"))

    if a.resume:
        if not a.decision:
            ap.error("--resume needs --decision")
        state = agent.load(a.resume)
        state = agent.resume(state, Decision(a.decision, json.loads(a.args) if a.args else None, a.note, "cli-user"))
    else:
        state = agent.start(a.task)

    human = iter(OFFLINE_HUMAN) if a.offline else None
    while state.status == "waiting_approval":
        if a.async_mode:
            path = agent.save(state)
            c = state.awaiting
            print(f"\nPAUSED waiting for approval of {c.name}({c.arguments}).\nCheckpoint: {path}\n"
                  f"Resume with: python {sys.argv[0]} --resume {path} --decision approve|reject|edit [--args JSON]")
            return
        decision = next(human) if human else ask_human(state)
        if human:
            print(f"\n>>> [scripted human] {decision.action} {state.awaiting.name} {decision.edited_args or ''}")
        state = agent.resume(state, decision)

    print_final(state)


if __name__ == "__main__":
    main()
