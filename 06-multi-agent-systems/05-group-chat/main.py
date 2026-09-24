"""Run: python 06-multi-agent-systems/05-group-chat/main.py "Plan 3 days in Goa under INR 30k" --selector llm [--offline]"""
import argparse

from group_chat import (TRIP_RULES, GroupChat, LLMSelector, RoundRobinSelector, RuleBasedSelector, llm_for, offline_llm,
                        trip_team)

p = argparse.ArgumentParser()
p.add_argument("task", nargs="?", default="Plan a 3-day Goa trip for 2 people under INR 30,000")
p.add_argument("--selector", choices=["round_robin", "rules", "llm"], default="llm")
p.add_argument("--max-turns", type=int, default=10)
p.add_argument("--offline", action="store_true")
args = p.parse_args()

fake = offline_llm() if args.offline else None
factory = (lambda r: fake) if fake else llm_for
selector = {
    "round_robin": RoundRobinSelector,
    "rules": lambda: RuleBasedSelector(TRIP_RULES),
    "llm": lambda: LLMSelector(factory("manager")),
}[args.selector]()

res = GroupChat(trip_team(factory), selector, max_turns=args.max_turns).run(args.task)
print()
for m in res.transcript:
    print(f"{m.speaker:>14}: {m.content}")
print(f"\n[stopped: {res.stopped_reason} after {res.turns} turns, selector={args.selector}]")
