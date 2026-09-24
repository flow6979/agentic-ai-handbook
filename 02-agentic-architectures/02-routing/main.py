"""Run: python 02-agentic-architectures/02-routing/main.py [--offline] ["ticket text" ...]

Real mode: ROUTER/CHEAP/STRONG models env se aate hain (fallback: LLM_MODEL):
  ROUTER_MODEL=groq:llama-3.1-8b-instant CHEAP_MODEL=groq:llama-3.1-8b-instant STRONG_MODEL=groq:llama-3.3-70b-versatile
"""
import argparse
import os

from routing_router import handle_ticket, offline_handler_llm, offline_router_llm

from agentkit import get_llm

SAMPLES = [
    "I was charged twice for my subscription this month",
    "I want my money back for order #123",
    "App shows error 500 when I login",
    "Can you add dark mode?",
    "something weird is happening",
    "Explain why my webhook retries keep failing? Compare exponential backoff vs fixed? ```Traceback: TimeoutError```",
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("tickets", nargs="*")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()

    if args.offline:
        router, cheap, strong = offline_router_llm(), offline_handler_llm("cheap"), offline_handler_llm("strong")
    else:
        router = get_llm(os.getenv("ROUTER_MODEL"))
        cheap = get_llm(os.getenv("CHEAP_MODEL"))
        strong = get_llm(os.getenv("STRONG_MODEL"))

    for text in args.tickets or SAMPLES:
        r = handle_ticket(text, router, cheap, strong)
        print(f"\nTICKET : {text}")
        print(f"ROUTE  : {r.route} (via {r.method}) model={r.model} human={r.needs_human}")
        print(f"REPLY  : {r.reply[:300]}")


if __name__ == "__main__":
    main()
