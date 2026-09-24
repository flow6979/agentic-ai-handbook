"""Run: python 02-agentic-architectures/03-parallelization/main.py [review|moderate|both] [--offline]"""
import argparse
import asyncio

from parallel_sectioning import SAMPLE_CODE, review_code_async, review_code_threads
from parallel_sectioning import offline_demo_llm as review_llm
from parallel_voting import moderate
from parallel_voting import offline_demo_llm as vote_llm

from agentkit import get_llm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mode", nargs="?", default="both", choices=["review", "moderate", "both"])
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.mode in ("review", "both"):
        llm = review_llm() if args.offline else get_llm()
        print("=== SECTIONING: 3 reviewers in parallel (threads) ===")
        rep = review_code_threads(llm, SAMPLE_CODE)
        for r in rep.reviews:
            print(f"- {r.aspect:12} {r.severity:6} {r.findings}")
        print(f"overall={rep.overall} failed={rep.failed_aspects} took={rep.seconds}s (sequential would be ~3x)")
        print("\n=== SECTIONING: same thing with asyncio.gather ===")
        rep2 = asyncio.run(review_code_async(review_llm() if args.offline else llm, SAMPLE_CODE))
        print(f"overall={rep2.overall} took={rep2.seconds}s")

    if args.mode in ("moderate", "both"):
        print("\n=== VOTING: 5 moderators ===")
        for comment in ["Thanks, this fixed my bug!", "You are an idiot, delete your account"]:
            v = moderate(vote_llm() if args.offline else get_llm(), comment)
            print(f"{comment!r:45} -> {v.decision} (unsafe {v.unsafe_count}/{len(v.votes)}, invalid {v.invalid})")


if __name__ == "__main__":
    main()
