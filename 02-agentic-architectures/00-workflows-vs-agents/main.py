"""Run: python 02-agentic-architectures/00-workflows-vs-agents/main.py [--offline] [--user u1]"""
import argparse

from spectrum_demo import offline_agent_llm, offline_chain_llm, run_as_agent, run_as_chain

from agentkit import Tracer, get_llm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="use a scripted fake LLM (no API key)")
    p.add_argument("--user", default="u1")
    args = p.parse_args()

    chain_llm = offline_chain_llm() if args.offline else get_llm()
    agent_llm = offline_agent_llm() if args.offline else get_llm()

    print("=== 1) WORKFLOW (code decides the steps) ===")
    out = run_as_chain(chain_llm, args.user)
    print(out.total)
    print(out.message)
    print(f"LLM calls: {out.llm_calls}\n")

    print("=== 2) AGENT (LLM decides the steps) ===")
    res = run_as_agent(agent_llm, f"What's my cart total with tax? My user id is {args.user}.", tracer=Tracer(name="cart-agent"))
    print(res.output)
    print(f"LLM calls: {res.steps}  tokens: {res.usage}")


if __name__ == "__main__":
    main()
