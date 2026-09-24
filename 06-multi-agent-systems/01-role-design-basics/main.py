"""Run: python 06-multi-agent-systems/01-role-design-basics/main.py "What is an API?" [--offline]"""
import argparse

from role_design import EDITOR, WRITER, llm_for, offline_llm, write_with_editor

p = argparse.ArgumentParser()
p.add_argument("topic", nargs="?", default="What is an API?")
p.add_argument("--offline", action="store_true", help="fake LLM, no key needed")
p.add_argument("--show-prompts", action="store_true", help="print the generated role system prompts")
args = p.parse_args()

if args.show_prompts:
    print("----- WRITER system prompt -----\n" + WRITER.system_prompt())
    print("\n----- EDITOR system prompt -----\n" + EDITOR.system_prompt() + "\n")

fake = offline_llm() if args.offline else None
result = write_with_editor(args.topic, llm_factory=(lambda role: fake) if fake else llm_for)

for role, out in result.history:
    print(f"\n[{role}]\n{out}")
print(f"\n=== FINAL (after {result.rounds} editor round(s)) ===\n{result.final_text}")
