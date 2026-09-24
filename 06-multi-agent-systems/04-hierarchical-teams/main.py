"""Run: python 06-multi-agent-systems/04-hierarchical-teams/main.py "Launch a habit-tracker mobile app" [--offline]"""
import argparse

from hierarchical_teams import LaunchManager, llm_for, offline_llm

p = argparse.ArgumentParser()
p.add_argument("goal", nargs="?", default="Launch a habit-tracker mobile app next month")
p.add_argument("--offline", action="store_true")
args = p.parse_args()

fake = offline_llm() if args.offline else None
res = LaunchManager(llm_factory=(lambda r: fake) if fake else llm_for).run(args.goal)

for r in res.reports:
    print(f"\n######## {r.team.upper()} TEAM — {r.objective}")
    for w, o in r.worker_outputs.items():
        print(f"  --- {w} ---\n  " + o.replace("\n", "\n  "))
    print(f"  >> team report: {r.summary}")
if res.skipped:
    print(f"\n(skipped invalid names: {res.skipped})")
print(f"\n=== FINAL LAUNCH PLAN ===\n{res.final}")
