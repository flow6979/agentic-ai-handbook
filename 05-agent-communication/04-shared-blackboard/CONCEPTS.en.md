**Language:** [Hinglish](CONCEPTS.md) · English

# 04 · Shared Blackboard (collaboration over shared state)

## Basic idea

Imagine a classroom with a **whiteboard**. Different experts (a flight expert, a hotel expert,
a budget expert) stand in front of it. Nobody talks to anybody. Each expert looks at the board:
*"is there something here I can add value to?"* If yes, they write their part on the board.
Then the others see what was just written and do their own work.

That is the **Blackboard Architecture** (an AI pattern from the 1970s, from the Hearsay-II speech system).
In today's multi-agent systems it goes by the name **"shared state"** (LangGraph's `State`
is exactly this concept).

```
                  ┌───────────────── BLACKBOARD ─────────────────┐
                  │ query:      "4 nights Goa from Delhi, 25000" │
                  │ request:    {origin, destination, nights, …} │
                  │ flight:     AI-101 (7800)                    │
                  │ hotel:      Sea Breeze Inn                   │
                  │ hotel_hint: "cheaper"                        │
                  │ budget_ok:  {total: 21800}                   │
                  │ itinerary:  "Day 1 ..."                      │
                  └──────▲──────▲──────▲──────▲──────▲───────────┘
                    read/│ write│      │      │      │
                  ┌──────┴┐ ┌───┴───┐ ┌┴────┐ ┌┴─────┐ ┌┴─────────┐
                  │parser │ │flights│ │hotel│ │budget│ │itinerary │
                  │ (LLM) │ │       │ │     │ │      │ │  (LLM)   │
                  └───────┘ └───────┘ └─────┘ └──────┘ └──────────┘
                        ▲
                        │ "who runs next?"
                  ┌─────┴──────┐
                  │ CONTROLLER │
                  └────────────┘
```

## Three parts

1. **Blackboard**: a shared data store (key → value) + history (who wrote what, when)
2. **Knowledge Sources (agents)**: each has two methods:
   - `can_contribute(board)`: can I do something given the board's current state?
   - `contribute(board)`: do my work and update the board
3. **Controller**: a loop that decides who runs now, and when to stop

## Controller loop

```
 ┌─► is the goal (itinerary) on the board? ──yes──► STOP ✓
 │         │ no
 │         ▼
 │   is there an error? ──yes──► STOP ✗
 │         │ no
 │         ▼
 │   ready = [agents whose can_contribute() == True]
 │         │
 │   ready empty? ──yes──► STOP (deadlock: nobody can move forward)
 │         │ no
 │         ▼
 │   run the first ready agent (priority order)
 └─────────┘   (with a max_iterations guard)
```

## Conflict resolution: what if the budget breaks?

This is the most elegant part of a blackboard: **agents can "undo" each other's work and leave a hint**.

```
 hotels:  hotel = Taj (9000/night, rating 4.8)
 budget:  7800 + 9000×4 = 43800 > 25000 ✗
          → rejected_hotels += Taj
          → hotel_hint = "cheaper"
          → DELETE hotel
 hotels:  can_contribute? there is no "hotel" key → yes!
          hint = cheaper → best-rated option cheaper than Taj → Sea Breeze (3500)
 budget:  7800 + 3500×4 = 21800 ≤ 25000 ✓ → budget_ok
 itinerary: can run now
```

No agent "called" any other agent. Everything happened through the board.

## Implementations (subtypes of the store)

| Store | When |
|---|---|
| `InMemoryBlackboard` (dict + Lock) | one process, thread safe |
| `SqliteBlackboard` | state survives a restart, or multiple processes share one file |
| Redis hash / Postgres (real world) | distributed agents, multiple machines |
| LangGraph `State` + checkpointer | graph-based agents, time-travel debugging |

**Why the lock?** If two agent threads write at the same time, you can get a race condition. A `threading.Lock`
or a DB transaction ensures only one writes at a time.

## Scheduling policies (controller variants)

- **Priority order** (this project): the first ready agent in the list
- **Opportunistic**: every ready agent gets a turn each round
- **LLM-controller**: an LLM looks at the board and decides who runs (like a supervisor)
- **Parallel**: all ready agents run together in threads (the lock is required)

## Blackboard vs message passing

| | Message passing (01) | Blackboard (04) |
|---|---|---|
| Coupling | The sender must know the recipient's name | Nobody knows anybody, only the board keys |
| Adding a new agent | Callers have to change | Just add it to the list |
| Where state lives | Scattered across messages | In one place, a full snapshot |
| Debugging | Message log | Board history (who/when/what) |
| Risk | Chatty, cycles | Everyone depends on the board schema, contention |

## When to use it / when not to

**Use it:** when the problem is solved incrementally, several specialists combine partial results,
the order is not fixed in advance (conflicts/retries happen), or you want the whole state in one place.

**Do not use it:** for a simple linear pipeline (use a straight chain), or when you have very high-frequency writes
(contention).

## Pitfalls

- **Key naming chaos**: document the board's schema (here it is at the top of `blackboard_trip.py`)
- **Deadlock**: no agent is ready and the goal is not reached → the controller should detect it and stop
- **Livelock**: A writes, B erases, A writes again... → `max_iterations` and `rejected_*` memory
- **Debugging without history** → keep the author + timestamp of every write

## How this project uses it

| Concept | Where |
|---|---|
| Blackboard interface + 2 stores | `blackboard_store.py` |
| Thread safety (Lock), transactions (sqlite) | `InMemoryBlackboard`, `SqliteBlackboard.set` |
| Audit trail | `history()` |
| Knowledge sources | `blackboard_trip.py` → `RequestParser` (LLM), `FlightAgent`, `HotelAgent`, `BudgetAgent`, `ItineraryAgent` (LLM) |
| Structured LLM output on the board | `RequestParser` → `llm_json(..., TripRequest)` |
| Conflict resolution (delete + hint) | `BudgetAgent.contribute` |
| Controller loop, deadlock/goal/max_iter | `Controller.run` |
