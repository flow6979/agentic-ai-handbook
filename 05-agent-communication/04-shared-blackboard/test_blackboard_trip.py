import threading

import pytest

from agentkit import ScriptedLLM
from blackboard_store import InMemoryBlackboard, SqliteBlackboard
from blackboard_trip import build_planner


def fake_llm(budget: int, origin: str = "Delhi"):
    def fake(messages, tools):
        p = messages[-1].content or ""
        if p.startswith("Extract"):
            return f'{{"origin": "{origin}", "destination": "Goa", "nights": 4, "budget": {budget}}}'
        return "Day 1 ... Day 5"

    return ScriptedLLM(fake)


@pytest.mark.parametrize("board_cls", [InMemoryBlackboard, SqliteBlackboard])
def test_budget_conflict_makes_hotel_agent_retry_cheaper(board_cls):
    board = board_cls()
    board.set("query", "Goa trip", author="user")
    ctrl = build_planner(fake_llm(25000), board, verbose=False)
    final = ctrl.run()

    # Non-stop 7800 <= 40% of 25000 -> AI-101. Taj (9000*4 + 7800) > budget -> Sea Breeze (3500*4 + 7800) = 21800
    assert final["flight"]["id"] == "AI-101"
    assert final["hotel"]["name"] == "Sea Breeze Inn"
    assert final["budget_ok"] == {"total": 21800, "budget": 25000}
    assert final["itinerary"] == "Day 1 ... Day 5"
    # Budget agent ne conflict pakda aur hotel agent dobara chala
    assert ctrl.trace == ["parser", "flights", "hotels", "budget", "hotels", "budget", "itinerary"]
    assert any(h["op"] == "delete" and h["key"] == "hotel" and h["author"] == "budget" for h in board.history())


def test_generous_budget_keeps_best_rated_hotel():
    board = InMemoryBlackboard()
    board.set("query", "luxury", author="user")
    final = build_planner(fake_llm(100000), board, verbose=False).run()
    assert final["hotel"]["name"] == "Taj Beach Resort" and final["flight"]["id"] == "AI-101"


def test_impossible_request_stops_with_error():
    board = InMemoryBlackboard()
    board.set("query", "x", author="user")
    final = build_planner(fake_llm(1000), board, verbose=False).run()
    assert "itinerary" not in final and "error" in final


def test_no_route_error():
    board = InMemoryBlackboard()
    board.set("query", "x", author="user")
    final = build_planner(fake_llm(50000, origin="Chennai"), board, verbose=False).run()
    assert final["error"].startswith("no flights")


def test_sqlite_board_persists_across_instances(tmp_path):
    path = str(tmp_path / "board.db")
    SqliteBlackboard(path).set("k", {"a": 1}, author="t")
    assert SqliteBlackboard(path).get("k") == {"a": 1}


def test_in_memory_board_is_thread_safe():
    board = InMemoryBlackboard()

    def writer(i):
        for j in range(200):
            board.set(f"k{i}-{j}", j, author=f"w{i}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(board.snapshot()) == 1600 and len(board.history()) == 1600
