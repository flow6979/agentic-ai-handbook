"""ReWOO demo + ReAct ke saath token/LLM-call comparison.

    python 02-agentic-architectures/09-rewoo/main.py "How many times taller is Burj Khalifa than Qutub Minar?"
    python 02-agentic-architectures/09-rewoo/main.py --compare "..."     # same task ReAct se bhi
    python 02-agentic-architectures/09-rewoo/main.py --offline
"""
from __future__ import annotations

import argparse
import json

from agentkit import Agent, ScriptedLLM, Tracer, call, get_llm, tool_response

from rewoo_agent import ReWOO
from rewoo_tools import TOOLS

TASK = "How many times taller is Mount Everest than the Eiffel Tower, and what is that ratio times the population of Japan in millions?"


def estimate_input_tokens(llm: ScriptedLLM, tool_schemas: list | None = None) -> int:
    """Offline fake LLM ke liye fair estimate (~4 chars = 1 token): har call pe bheja gaya POORA payload
    gino: message text + tool call args + (native tool calling mein) har call ke saath jaane wale tool schemas."""
    schema_chars = len(json.dumps(tool_schemas)) if tool_schemas else 0
    total = 0
    for msgs in llm.calls:
        chars = schema_chars
        for m in msgs:
            chars += len(m.content or "") + sum(len(c.name) + len(json.dumps(c.arguments)) for c in m.tool_calls or [])
        total += chars // 4
    return total


def offline_llms() -> tuple[ScriptedLLM, ScriptedLLM]:
    rewoo_llm = ScriptedLLM([
        "Plan: Find Everest's height.\n#E1 = lookup[mount everest height in metres]\n"
        "Plan: Find the Eiffel Tower's height.\n#E2 = lookup[eiffel tower height in metres]\n"
        "Plan: Find Japan's population.\n#E3 = lookup[population of japan in millions]\n"
        "Plan: Compute the ratio.\n#E4 = calculator[#E1 / #E2]\n"
        "Plan: Multiply the ratio by the population.\n#E5 = calculator[#E4 * #E3]",
        "Everest is about 26.8x taller than the Eiffel Tower; 26.8155 x 124 ≈ 3325.1.",
    ])
    react_llm = ScriptedLLM([
        tool_response(call("lookup", query="mount everest height in metres")),
        tool_response(call("lookup", query="eiffel tower height in metres")),
        tool_response(call("lookup", query="population of japan in millions")),
        tool_response(call("calculator", expression="8849 / 330")),
        tool_response(call("calculator", expression="26.8152 * 124")),
        "Everest is about 26.8x taller; times 124 ≈ 3325.1.",
    ])
    return rewoo_llm, react_llm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default=TASK)
    ap.add_argument("--compare", action="store_true", help="also run ReAct on the same task")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    if args.offline:
        rewoo_llm, react_llm = offline_llms()
        args.task, args.compare = TASK, True
    else:
        rewoo_llm = react_llm = get_llm()

    print("=== ReWOO ===")
    r = ReWOO(rewoo_llm, TOOLS, tracer=Tracer(name="rewoo")).run(args.task)
    print(f"parallel levels: {r.levels}")
    print(f"ANSWER: {r.answer}")
    rewoo_in = estimate_input_tokens(rewoo_llm) if args.offline else r.usage.input_tokens
    print(f"ReWOO  -> llm_calls={r.llm_calls}  input_tokens={rewoo_in}")

    if args.compare:
        print("\n=== ReAct (native tool calling) on the same task ===")
        a = Agent(react_llm, TOOLS, "Use tools to answer. Look up facts, use calculator for math.",
                  name="react", tracer=Tracer(name="react")).run(args.task)
        print(f"ANSWER: {a.output}")
        schemas = [t.spec.__dict__ for t in TOOLS]
        react_in = estimate_input_tokens(react_llm, schemas) if args.offline else a.usage.input_tokens
        print(f"ReAct  -> llm_calls={a.steps}  input_tokens={react_in}")
        if args.offline:
            print("(offline: tokens = estimate of the full payload sent per call, ~4 chars/token)")
        print("\nNote: ReAct har call pe poori history + tool schemas dobara bhejta hai, isliye input tokens tezi se badhte hain.")


if __name__ == "__main__":
    main()
