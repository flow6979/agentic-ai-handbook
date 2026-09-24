"""Web page reader agent: URL kholo, main content nikaalo, relevant hissa padh ke jawab do.

Run (repo root se):
    python 03-web-agents/03-web-page-reader/main.py --offline
    python 03-web-agents/03-web-page-reader/main.py "How do honeybees communicate? Read https://en.wikipedia.org/wiki/Waggle_dance"
    python 03-web-agents/03-web-page-reader/main.py --raw https://en.wikipedia.org/wiki/Honey_bee   # sirf extracted text dekho
"""
from __future__ import annotations

import argparse

from agentkit import Agent, get_llm

from pagereader_fetch import PageFetcher
from pagereader_tools import SYSTEM, make_reader_tool


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?",
                   default="How do honeybees tell each other where flowers are? Use https://encyclopedia.example/wiki/honeybee")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--raw", metavar="URL", help="just fetch + extract a URL and print the text (no LLM)")
    args = p.parse_args()

    if args.offline:
        from pagereader_fixtures import fake_resolver, offline_client, offline_llm

        fetcher, llm = PageFetcher(offline_client(), resolver=fake_resolver), offline_llm()
    else:
        fetcher, llm = PageFetcher(), None

    if args.raw:
        page = fetcher.fetch(args.raw)
        print(f"# {page.title}\n({page.final_url}, {page.content_type}, {len(page.text)} chars, truncated={page.truncated})\n")
        print(page.text[:3000])
        return

    agent = Agent(llm or get_llm(), [make_reader_tool(fetcher)], SYSTEM, name="reader", max_steps=5)
    print("\n" + agent.run(args.question).output)


if __name__ == "__main__":
    main()
