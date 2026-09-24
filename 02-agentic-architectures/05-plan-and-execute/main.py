"""Plan-and-Execute demo: trip planner jo fail hone pe replan karta hai.

    python 02-agentic-architectures/05-plan-and-execute/main.py "Plan a 2-night trip from Delhi to Goa with flight + hotel cost"
    python 02-agentic-architectures/05-plan-and-execute/main.py --offline
"""
from __future__ import annotations

import argparse
import json

from agentkit import ScriptedLLM, Tracer, call, get_llm, tool_response

from planexec_agent import PlanAndExecute
from planexec_tools import TOOLS

OFFLINE_GOAL = ("Plan a 2-night weekend trip from Delhi. Kasol preferred; if not reachable, pick another city "
                "with a direct flight and good weather. Tell me the total flight + hotel cost.")


def offline_llm() -> ScriptedLLM:
    j = json.dumps
    return ScriptedLLM([
        # 1. PLANNER
        j({"steps": [{"description": "Find flights from Delhi to Kasol"},
                     {"description": "Find hotels in Kasol"},
                     {"description": "Compute total cost for 2 nights"}]}),
        # 2. EXECUTOR step 1 -> tool fails -> FAILED
        tool_response(call("search_flights", origin="Delhi", destination="Kasol")),
        "FAILED: there are no flights from Delhi to Kasol.",
        # 3. REPLANNER -> replan
        j({"action": "replan", "reason": "Kasol has no flights; switch to Jaipur (direct flight, clear weather)",
           "new_steps": [{"description": "Check weather in Jaipur"},
                         {"description": "Find flights from Delhi to Jaipur"},
                         {"description": "Find hotels in Jaipur"},
                         {"description": "Compute total cost: cheapest flight + 2 nights hotel"}]}),
        # 4. weather
        tool_response(call("get_weather", city="Jaipur")), "Jaipur weather: clear, 24C",
        j({"action": "continue", "reason": "weather is good"}),
        # 5. flights
        tool_response(call("search_flights", origin="Delhi", destination="Jaipur")), "Cheapest: IndiGo 2900 INR",
        j({"action": "continue"}),
        # 6. hotels
        tool_response(call("search_hotels", city="Jaipur")), "Pink Haveli, 2800 INR/night",
        j({"action": "continue"}),
        # 7. total
        tool_response(call("calculator", expression="2900 + 2*2800")), "Total: 8500 INR",
        j({"action": "finish", "reason": "all info gathered",
           "final_answer": "Kasol has no direct flights, so: Jaipur (clear, 24C). IndiGo flight 2900 INR + "
                           "Pink Haveli 2 nights x 2800 INR = 8500 INR total."}),
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("goal", nargs="?", default=OFFLINE_GOAL)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    llm = offline_llm() if args.offline else get_llm()
    agent = PlanAndExecute(llm, TOOLS, tracer=Tracer(name="plan-exec"))
    res = agent.run(OFFLINE_GOAL if args.offline else args.goal)

    print("\n=== Plans (initial + replans) ===")
    for i, p in enumerate(res.plans):
        print(f"  v{i}: " + " -> ".join(p))
    print("\n=== Step history ===")
    for h in res.history:
        print(f"  {'✗' if h.failed else '✓'} {h.step}: {h.result}")
    print(f"\nFINAL ANSWER: {res.answer}\n(replans used: {res.replans})")


if __name__ == "__main__":
    main()
