"""Travel-helper agent: public APIs (weather, currency, Wikipedia) ko tools ki tarah use karta hai.

Run (repo root se):
    python 03-web-agents/01-api-tools/main.py --offline
    python 03-web-agents/01-api-tools/main.py "Tokyo ka weather kaisa hai aur 1000 INR kitne JPY?"
"""
from __future__ import annotations

import argparse

from agentkit import Agent, get_llm

from apitools_http import ApiClient
from apitools_tools import make_tools

SYSTEM = """You are a concise travel helper.
- Use tools for every fact: weather, currency, or facts about places. Never guess numbers.
- Call independent tools in the same step when possible.
- If a tool returns an error, say what failed instead of inventing data.
- End with a short 'Sources:' line naming which tools gave which facts."""

DEFAULT_Q = (
    "I'm visiting Paris for 3 days with 500 USD. What's the weather looking like, how many EUR is that, "
    "and give me one fact about the Eiffel Tower."
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?", default=DEFAULT_Q)
    p.add_argument("--offline", action="store_true", help="fake APIs + scripted LLM, no internet/keys")
    args = p.parse_args()

    if args.offline:
        from apitools_fixtures import offline_client, offline_llm

        api, llm = ApiClient(client=offline_client()), offline_llm()
    else:
        api, llm = ApiClient(), get_llm()

    agent = Agent(llm, make_tools(api), SYSTEM, name="travel", max_steps=6)
    result = agent.run(args.question)
    print("\n" + result.output)
    print(f"\n[steps={result.steps} tokens={result.usage.input_tokens}+{result.usage.output_tokens} http={api.stats}]")


if __name__ == "__main__":
    main()
