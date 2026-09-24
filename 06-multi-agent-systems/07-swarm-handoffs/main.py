"""Interactive support chat.
Run: python 06-multi-agent-systems/07-swarm-handoffs/main.py [--offline]
Try: "I want a refund for order A100" / "where is my order A200?" / "my wifi router is not working"
"""
import argparse

from swarm_handoffs import Swarm, build_support_swarm, llm_for, offline_llm

p = argparse.ArgumentParser()
p.add_argument("--offline", action="store_true")
p.add_argument("--once", help="send one message and exit (non-interactive)")
args = p.parse_args()

fake = offline_llm() if args.offline else None
swarm = Swarm(build_support_swarm(), llm_factory=(lambda r: fake) if fake else llm_for)
context = {"customer_id": "C1"}
history, active = [], "triage"

while True:
    text = args.once or input("\nyou> ").strip()
    if text in ("exit", "quit", ""):
        break
    # Conversation + active agent persist -> agla message usi agent ke paas jata hai
    res = swarm.run(text, start=active, context=context, history=history)
    history, active = res.messages, res.active_agent
    print(f"{res.active_agent}> {res.reply}\n   [path: {' -> '.join(res.path)} | context: {res.context}]")
    if args.once:
        break
