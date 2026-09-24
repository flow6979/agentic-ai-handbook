"""Trip planner on a blackboard.

Board keys (sab agents inhi ke through coordinate karte hain):
    query          user ka raw text
    request        {origin, destination, nights, budget}     <- RequestParser (LLM)
    flight         chosen flight                              <- FlightAgent
    hotel          chosen hotel                               <- HotelAgent
    hotel_hint     "cheaper" agar budget toot gaya            <- BudgetAgent
    budget_ok      {total, budget}                            <- BudgetAgent
    itinerary      final plan text                            <- ItineraryAgent (LLM)

Controller loop:  jo agent `can_contribute(board)` bole, usko chalao; repeat jab tak
itinerary na ban jaye (ya koi agent kuch na kar sake / max iterations).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from agentkit import LLM, NullTracer, Tracer, llm_json

from blackboard_store import Blackboard

FLIGHTS = [
    {"id": "AI-101", "from": "Delhi", "to": "Goa", "price": 7800, "stops": 0},
    {"id": "6E-202", "from": "Delhi", "to": "Goa", "price": 5200, "stops": 1},
    {"id": "SG-303", "from": "Mumbai", "to": "Goa", "price": 3100, "stops": 0},
]
HOTELS = [
    {"name": "Taj Beach Resort", "city": "Goa", "per_night": 9000, "rating": 4.8},
    {"name": "Sea Breeze Inn", "city": "Goa", "per_night": 3500, "rating": 4.2},
    {"name": "Backpacker Hostel", "city": "Goa", "per_night": 900, "rating": 3.9},
]


class TripRequest(BaseModel):
    origin: str
    destination: str
    nights: int
    budget: int


class KnowledgeSource:
    """Blackboard terminology mein har specialist agent ek 'knowledge source' hai."""

    name = "ks"

    def can_contribute(self, board: Blackboard) -> bool: ...

    def contribute(self, board: Blackboard) -> None: ...


class RequestParser(KnowledgeSource):
    name = "parser"

    def __init__(self, llm: LLM):
        self.llm = llm

    def can_contribute(self, board):
        return board.has("query") and not board.has("request")

    def contribute(self, board):
        req = llm_json(self.llm, f"Extract the trip request from: {board.get('query')!r}", TripRequest,
                       system="You extract structured travel requests. Budget in INR as integer.")
        board.set("request", req.model_dump(), author=self.name)


class FlightAgent(KnowledgeSource):
    name = "flights"

    def can_contribute(self, board):
        return board.has("request") and not board.has("flight")

    def contribute(self, board):
        r = board.get("request")
        options = [f for f in FLIGHTS if f["from"].lower() == r["origin"].lower() and f["to"].lower() == r["destination"].lower()]
        if not options:
            board.set("error", f"no flights {r['origin']} -> {r['destination']}", author=self.name)
            return
        # Prefer non-stop agar woh budget ke 40% ke andar hai, warna sabse sasta
        nonstop = [f for f in options if f["stops"] == 0 and f["price"] <= 0.4 * r["budget"]]
        board.set("flight", min(nonstop or options, key=lambda f: f["price"]), author=self.name)


class HotelAgent(KnowledgeSource):
    name = "hotels"

    def can_contribute(self, board):
        return board.has("request") and not board.has("hotel")

    def contribute(self, board):
        r = board.get("request")
        options = [h for h in HOTELS if h["city"].lower() == r["destination"].lower()]
        tried = set(board.get("rejected_hotels", []))
        options = [h for h in options if h["name"] not in tried]
        if not options:
            board.set("error", "no hotel fits the budget", author=self.name)
            return
        if board.get("hotel_hint") == "cheaper":
            # Budget agent ne bola sasta chahiye: rejected se saste options mein best-rated lo
            ceiling = min(h["per_night"] for h in HOTELS if h["name"] in tried)
            options = [h for h in options if h["per_night"] < ceiling]
            if not options:
                board.set("error", "no hotel fits the budget", author=self.name)
                return
        pick = max(options, key=lambda h: h["rating"])
        board.set("hotel", pick, author=self.name)


class BudgetAgent(KnowledgeSource):
    name = "budget"

    def can_contribute(self, board):
        return board.has("flight", "hotel") and not board.has("budget_ok")

    def contribute(self, board):
        r, f, h = board.get("request"), board.get("flight"), board.get("hotel")
        total = f["price"] + h["per_night"] * r["nights"]
        if total <= r["budget"]:
            board.set("budget_ok", {"total": total, "budget": r["budget"]}, author=self.name)
        else:
            # Conflict resolution: hotel hatao, hint likho; HotelAgent phir se try karega
            board.set("rejected_hotels", [*board.get("rejected_hotels", []), h["name"]], author=self.name)
            board.set("hotel_hint", "cheaper", author=self.name)
            board.delete("hotel", author=self.name)


class ItineraryAgent(KnowledgeSource):
    name = "itinerary"

    def __init__(self, llm: LLM):
        self.llm = llm

    def can_contribute(self, board):
        return board.has("budget_ok") and not board.has("itinerary")

    def contribute(self, board):
        s = board.snapshot()
        text = self.llm.complete(
            f"Write a short day-by-day itinerary.\nRequest: {s['request']}\nFlight: {s['flight']}\n"
            f"Hotel: {s['hotel']}\nTotal cost: {s['budget_ok']['total']} INR.",
            system="You are a friendly travel planner. Be concise.",
        )
        board.set("itinerary", text.strip(), author=self.name)


@dataclass
class Controller:
    board: Blackboard
    sources: list[KnowledgeSource]
    max_iterations: int = 20
    tracer: Tracer = field(default_factory=lambda: NullTracer("controller"))
    trace: list[str] = field(default_factory=list)

    def run(self, goal_key: str = "itinerary") -> dict[str, Any]:
        for _ in range(self.max_iterations):
            if self.board.has(goal_key) or self.board.has("error"):
                break
            ready = [ks for ks in self.sources if ks.can_contribute(self.board)]
            if not ready:
                self.tracer.event("error", "no agent can make progress; stopping")
                break
            ks = ready[0]  # scheduling policy: list order = priority (simplest)
            self.tracer.event("tool", f"{ks.name} contributes")
            self.trace.append(ks.name)
            ks.contribute(self.board)
        return self.board.snapshot()


def build_planner(llm: LLM, board: Blackboard, verbose: bool = True) -> Controller:
    sources = [RequestParser(llm), FlightAgent(), HotelAgent(), BudgetAgent(), ItineraryAgent(llm)]
    return Controller(board, sources, tracer=Tracer(name="controller") if verbose else NullTracer("controller"))
