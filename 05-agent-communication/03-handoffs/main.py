"""Interactive support chat with handoffs.

    python 05-agent-communication/03-handoffs/main.py            # real LLM, chat loop
    python 05-agent-communication/03-handoffs/main.py --offline  # scripted demo
"""
from __future__ import annotations

import argparse

from agentkit import ScriptedLLM, Tracer, call, get_llm, tool_response

from handoff_support import build_agents
from handoff_swarm import Swarm


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM([
        tool_response(call("transfer_to_billing", reason="double charge")),
        tool_response(call("list_invoices")),
        tool_response(call("refund_invoice", invoice_id="INV-2")),
        "I've refunded the duplicate charge INV-2 (499). Anything else?",
        # user ka agla message: login issue -> billing wapas triage ko deta hai
        tool_response(call("transfer_to_triage", reason="not billing")),
        tool_response(call("transfer_to_tech", reason="account locked")),
        tool_response(call("account_status")),
        tool_response(call("unlock_account")),
        "Your account is unlocked and a reset link is on its way.",
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    swarm = Swarm(offline_llm() if args.offline else get_llm(), build_agents(), tracer=Tracer(name="swarm"))
    ctx = {"customer_id": "C-101"}
    history, active = [], "triage"
    turns = iter(["I was charged twice this month!", "Also I can't log in, it says account locked."]) if args.offline else None

    while True:
        try:
            text = next(turns) if turns else input("\nyou> ")
        except (StopIteration, EOFError, KeyboardInterrupt):
            break
        if text.strip() in {"", "exit", "quit"}:
            break
        if turns:
            print(f"\nyou> {text}")
        res = swarm.run(text, start=active, history=history, context=ctx)
        history, active = res.messages, res.active_agent  # agla turn wahi agent continue karega
        print(f"{res.active_agent}> {res.output}   (path: {' -> '.join(res.handoff_path)})")


if __name__ == "__main__":
    main()
