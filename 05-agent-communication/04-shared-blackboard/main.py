"""Trip planner using a shared blackboard.

    python 05-agent-communication/04-shared-blackboard/main.py "4 nights in Goa from Delhi, budget 25000"
    python 05-agent-communication/04-shared-blackboard/main.py --offline
    python 05-agent-communication/04-shared-blackboard/main.py --offline --sqlite trip.db   # board file mein
"""
from __future__ import annotations

import argparse
import json

from agentkit import ScriptedLLM, get_llm

from blackboard_store import InMemoryBlackboard, SqliteBlackboard
from blackboard_trip import build_planner


def offline_llm() -> ScriptedLLM:
    def fake(messages, tools):
        p = messages[-1].content or ""
        if p.startswith("Extract"):
            return '{"origin": "Delhi", "destination": "Goa", "nights": 4, "budget": 25000}'
        return "Day 1: Fly in, beach sunset.\nDay 2: North Goa forts.\nDay 3: Spice farm.\nDay 4: Relax.\nDay 5: Fly back."

    return ScriptedLLM(fake)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="4 nights in Goa from Delhi, budget 25000 rupees")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--sqlite", help="path to a sqlite file for the board (default: in-memory dict)")
    args = ap.parse_args()

    board = SqliteBlackboard(args.sqlite) if args.sqlite else InMemoryBlackboard()
    board.set("query", args.query, author="user")
    ctrl = build_planner(offline_llm() if args.offline else get_llm(), board)
    final = ctrl.run()

    print("\n=== WHO RAN, IN ORDER ===\n" + " -> ".join(ctrl.trace))
    print("\n=== BOARD HISTORY ===")
    for h in board.history():
        print(f"{h['author']:>9} {h['op']:<6} {h['key']:<16} {json.dumps(h['value'], ensure_ascii=False)[:90] if h['value'] is not None else ''}")
    print("\n=== RESULT ===")
    print(final.get("itinerary") or final.get("error"))


if __name__ == "__main__":
    main()
