"""Web search agent: search karo, results padho, citations ke saath jawab do.

Run (repo root se):
    python 03-web-agents/02-web-search/main.py --offline
    python 03-web-agents/02-web-search/main.py "What changed in Python 3.13?"
Provider: TAVILY_API_KEY set hai to Tavily, warna DuckDuckGo (no key).
"""
from __future__ import annotations

import argparse
from datetime import date

from agentkit import Agent, get_llm

from websearch_providers import DuckDuckGoProvider, get_search_provider
from websearch_tools import SearchLog, make_search_tool, verify_citations

SYSTEM = f"""You are a research assistant with a web_search tool. Today is {date.today().isoformat()}.
- Search before answering anything factual or recent. Do 1-3 searches, refine keywords if needed.
- Answer ONLY from the search results. If they don't contain the answer, say so.
- Cite with [n] in the text and end with 'Sources:' listing [n] <url>. Only use URLs from the results."""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?", default="What are the headline features of Python 3.13?")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.offline:
        from websearch_fixtures import offline_client, offline_llm

        provider, llm = DuckDuckGoProvider(offline_client()), offline_llm()
    else:
        provider, llm = get_search_provider(), get_llm()

    log = SearchLog()
    agent = Agent(llm, [make_search_tool(provider, log)], SYSTEM, name=f"search:{provider.name}", max_steps=6)
    result = agent.run(args.question)
    print("\n" + result.output)

    check = verify_citations(result.output, log)
    print(f"\n[queries={log.queries}]")
    print(f"[citations verified={len(check['verified'])} unverified={check['unverified']}]")
    if not check["has_citations"]:
        print("[warning: answer has no citations]")


if __name__ == "__main__":
    main()
