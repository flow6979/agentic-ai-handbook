"""Run: python 06-multi-agent-systems/02-sequential-crew/main.py "a CLI todo app" [--offline]"""
import argparse

from sequential_crew import SoftwareCrew, llm_for, offline_llm

p = argparse.ArgumentParser()
p.add_argument("idea", nargs="?", default="a tiny calculator library with an add function")
p.add_argument("--offline", action="store_true")
args = p.parse_args()

fake = offline_llm() if args.offline else None
crew = SoftwareCrew(llm_factory=(lambda role: fake) if fake else llm_for)
res = crew.kickoff(args.idea)

for name, out in res.outputs.items():
    print(f"\n===== {name.upper()} =====\n{out}")
print(f"\n===== FILES ({len(res.files)}) =====")
for path, code in res.files.items():
    print(f"--- {path} ---\n{code}")
print(f"QA passed={res.qa.passed} after {res.reworks} rework(s)")
