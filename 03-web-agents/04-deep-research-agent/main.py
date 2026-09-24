"""Deep research agent: ek topic do, cited markdown report lo.

Run (repo root se):
    python 03-web-agents/04-deep-research-agent/main.py --offline
    python 03-web-agents/04-deep-research-agent/main.py "State of solid-state batteries in 2026" --max-searches 5 --max-pages 6 -o report.md

Real mode 02-web-search (search) aur 03-web-page-reader (safe fetch + chunks) ke code ko reuse karta hai.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentkit import get_llm

from deepresearch_agent import Budget, DeepResearcher

HERE = Path(__file__).resolve().parent


def real_tools():
    # Sibling projects ka code reuse (copy-paste nahi). Production mein yeh ek shared package hota.
    sys.path[:0] = [str(HERE.parent / "02-web-search"), str(HERE.parent / "03-web-page-reader")]
    from pagereader_chunks import chunk_text, top_chunks
    from pagereader_fetch import PageFetcher
    from websearch_providers import dedupe, get_search_provider

    provider, fetcher = get_search_provider(), PageFetcher()

    def search(q: str) -> list[dict]:
        return [r.to_dict() for r in dedupe(provider.search(q, max_results=5))]

    def read(url: str, question: str) -> str:
        page = fetcher.fetch(url)
        return "\n".join(top_chunks(chunk_text(page.text), question, k=4))

    return search, read


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("topic", nargs="?", default="Solar power: cost trends, growth and main challenges")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--max-searches", type=int, default=6)
    p.add_argument("--max-pages", type=int, default=8)
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("-o", "--out", help="write report to this markdown file")
    args = p.parse_args()

    if args.offline:
        from deepresearch_fixtures import fake_read, fake_search, offline_llm

        llm, search, read = offline_llm(), fake_search, fake_read
    else:
        llm, (search, read) = get_llm(), real_tools()

    budget = Budget(max_searches=args.max_searches, max_pages=args.max_pages, max_rounds=args.rounds)
    result = DeepResearcher(llm, search, read, budget=budget).run(args.topic)

    print("\n" + result.report)
    print(f"\n[rounds={result.rounds} searches={budget.searches}/{budget.max_searches} "
          f"pages={budget.pages}/{budget.max_pages} notes={len(result.notes)} skipped={len(result.skipped)}]")
    if args.out:
        Path(args.out).write_text(result.report)
        print(f"[saved {args.out}]")


if __name__ == "__main__":
    main()
