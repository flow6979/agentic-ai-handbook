"""Run: python 02-agentic-architectures/01-prompt-chaining/main.py "topic" [--tone friendly] [--offline]"""
import argparse

from chaining_pipeline import GateError, offline_demo_llm, write_blog

from agentkit import get_llm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("topic", nargs="?", default="Python async for beginners")
    p.add_argument("--tone", default="friendly")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    llm = offline_demo_llm() if args.offline else get_llm()
    try:
        res = write_blog(llm, args.topic, args.tone)
    except GateError as e:
        print(f"Pipeline stopped at a gate: {e}")
        raise SystemExit(1)

    print("--- step log ---")
    for line in res.log:
        print(" ", line)
    print(f"\n--- outline ---\n{res.outline.title}: {res.outline.sections}")
    print(f"\n--- final post ---\n{res.final}")


if __name__ == "__main__":
    main()
