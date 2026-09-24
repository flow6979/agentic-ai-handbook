"""Run: python 02-agentic-architectures/07-evaluator-optimizer/main.py ["product brief"] [--offline]

Tip: generator aur evaluator alag models rakho (GEN_MODEL / EVAL_MODEL env), self-grading bias kam hota hai.
"""
import argparse
import os

from evalopt_loop import DEMO_BRIEF, offline_demo_llms, optimize

from agentkit import get_llm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("brief", nargs="?", default=DEMO_BRIEF)
    p.add_argument("--threshold", type=int, default=8)
    p.add_argument("--max-iters", type=int, default=4)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.offline:
        gen, ev = offline_demo_llms()
    else:
        gen, ev = get_llm(os.getenv("GEN_MODEL")), get_llm(os.getenv("EVAL_MODEL"))

    res = optimize(gen, ev, args.brief, threshold=args.threshold, max_iters=args.max_iters)
    for i, a in enumerate(res.history, 1):
        print(f"\n--- iteration {i} ---\n{a.draft}")
        print(f"hard_errors={a.hard_errors} scores={a.scores}\nfeedback={a.feedback!r}")
    print(f"\nSTOP: {res.stop_reason}\nBEST ({res.best.scores}):\n{res.best.draft}")


if __name__ == "__main__":
    main()
