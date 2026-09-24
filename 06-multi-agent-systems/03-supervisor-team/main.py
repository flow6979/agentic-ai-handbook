"""Run: python 06-multi-agent-systems/03-supervisor-team/main.py "Should I install solar panels at home?" [--offline]"""
import argparse

from supervisor_team import SupervisorTeam, llm_for, offline_llm

p = argparse.ArgumentParser()
p.add_argument("question", nargs="?", default="Should I install solar panels at home?")
p.add_argument("--offline", action="store_true")
p.add_argument("--max-rounds", type=int, default=8)
args = p.parse_args()

fake = offline_llm() if args.offline else None
team = SupervisorTeam(llm_factory=(lambda r: fake) if fake else llm_for, max_rounds=args.max_rounds)
res = team.run(args.question)

for i, e in enumerate(res.board, 1):
    print(f"\n--- {i}. {e.worker} (instruction: {e.instruction}) ---\n{e.output}")
print(f"\n=== ANSWER ({res.stopped_reason}, {res.rounds} rounds) ===\n{res.answer}")
