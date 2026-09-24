"""Reflection demos.

    python 02-agentic-architectures/06-reflection/main.py refine "Write a 3-line product tagline for a solar lamp. Must mention price under 999 INR and be in Hinglish."
    python 02-agentic-architectures/06-reflection/main.py reflexion            # coding task with unit tests
    python 02-agentic-architectures/06-reflection/main.py reflexion --lessons lessons.json
    python 02-agentic-architectures/06-reflection/main.py refine --offline
    python 02-agentic-architectures/06-reflection/main.py reflexion --offline
"""
from __future__ import annotations

import argparse
import json

from agentkit import ScriptedLLM, Tracer, get_llm

from reflection_reflexion import LessonMemory, solve_with_reflexion
from reflection_refine import self_refine

REFINE_TASK = ("Write a 2-sentence product description for a solar lamp. Requirements: mention the price "
               "(799 INR), the 12-hour battery, and end with a call to action.")

CODE_TASK = ("Write `is_palindrome(s: str) -> bool` that returns True if s reads the same backwards, "
             "ignoring case, spaces and punctuation.")
CODE_TESTS = [
    "assert is_palindrome('racecar') is True",
    "assert is_palindrome('A man, a plan, a canal: Panama') is True",
    "assert is_palindrome('hello') is False",
    "assert is_palindrome('') is True",
]


def offline_refine_llm() -> ScriptedLLM:
    j = json.dumps
    return ScriptedLLM([
        "Our solar lamp lights up your nights. Buy now!",
        j({"score": 4, "approved": False, "issues": ["Price 799 INR missing", "12-hour battery not mentioned",
                                                     "Only one real sentence before CTA"]}),
        "Our solar lamp gives you 12 hours of bright light on a single sunny day. At just 799 INR, "
        "it's the smartest buy for your home - order yours today!",
        j({"score": 9, "approved": True, "issues": []}),
    ])


def offline_reflexion_llm() -> ScriptedLLM:
    return ScriptedLLM([
        "```python\ndef is_palindrome(s: str) -> bool:\n    return s == s[::-1]\n```",
        "I compared the raw string, so case, spaces and punctuation broke the Panama test. "
        "Lesson: normalise input first (lowercase, keep only alphanumeric chars) before comparing.",
        "```python\ndef is_palindrome(s: str) -> bool:\n    t = [c.lower() for c in s if c.isalnum()]\n"
        "    return t == t[::-1]\n```",
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["refine", "reflexion"])
    ap.add_argument("task", nargs="?")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--lessons", help="JSON file to persist Reflexion lessons across runs")
    args = ap.parse_args()

    if args.mode == "refine":
        llm = offline_refine_llm() if args.offline else get_llm()
        task = REFINE_TASK if args.offline or not args.task else args.task
        res = self_refine(llm, task, tracer=Tracer(name="refine"))
        for i, r in enumerate(res.rounds, 1):
            print(f"\n--- round {i} (score {r.critique.score}) ---\n{r.draft}\nissues: {r.critique.issues}")
        print(f"\nFINAL (approved={res.approved}):\n{res.final}")
    else:
        llm = offline_reflexion_llm() if args.offline else get_llm()
        mem = LessonMemory(args.lessons)
        res = solve_with_reflexion(llm, CODE_TASK, CODE_TESTS, memory=mem, tracer=Tracer(name="reflexion"))
        for i, a in enumerate(res.attempts, 1):
            print(f"\n--- attempt {i}: {'PASS' if a.run.passed else 'FAIL'} ---\n{a.code}\n{a.run.output}")
            if a.reflection:
                print(f"LESSON: {a.reflection}")
        print(f"\nSOLVED: {res.solved} in {len(res.attempts)} attempt(s). Lessons in memory: {len(mem.lessons)}")


if __name__ == "__main__":
    main()
