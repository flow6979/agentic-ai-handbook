"""Demo: manager specialists ko tools ki tarah call karta hai.

    python 05-agent-communication/02-agent-as-tool/main.py "Sales went from 950 to 1200. What's the growth %? Write a tweet about it."
    python 05-agent-communication/02-agent-as-tool/main.py --offline
"""
from __future__ import annotations

import argparse
import json

from agentkit import ScriptedLLM, call, get_llm, tool_response

from agent_as_tool_team import build_team

DEFAULT_TASK = "Our sales went from 950 to 1200 units. What's the growth %? Then write a short launch post about it."


def offline_llms():
    manager = ScriptedLLM([
        tool_response(call("ask_math_expert", task="Percent change from 950 to 1200?")),
        tool_response(call("ask_copywriter", task="Write a short post: sales grew 26.32% (950 -> 1200 units).")),
        "Growth is 26.32%. Suggested post -> 'Up 26%!': Sales jumped from 950 to 1200 units.",
    ])
    math = ScriptedLLM([tool_response(call("percent_change", old=950, new=1200)), "26.32% growth (950 -> 1200)."])
    writer = ScriptedLLM(['{"headline": "Up 26%!", "body": "Sales jumped from 950 to 1200 units."}'])
    return manager, math, writer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default=DEFAULT_TASK)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    if args.offline:
        m, w, c = offline_llms()
    else:
        llm = get_llm()
        m = w = c = llm  # teeno same model; chaho to specialist ke liye sasta model do
    manager = build_team(m, w, c)
    res = manager.run(args.task)
    print("\n=== FINAL ===\n" + res.output)
    print("\n=== WHAT THE MANAGER SAW FROM SPECIALISTS ===")
    for msg in res.messages:
        if msg.role == "tool":
            print(msg.name, "->", json.dumps(json.loads(msg.content), ensure_ascii=False))


if __name__ == "__main__":
    main()
