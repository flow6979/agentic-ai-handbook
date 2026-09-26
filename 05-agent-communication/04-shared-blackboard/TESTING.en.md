**Language:** [Hinglish](TESTING.md) · English

# 04 · Shared Blackboard: how to test and tinker

## Offline demo

```bash
python 05-agent-communication/04-shared-blackboard/main.py --offline
```

Look at three things:
1. **WHO RAN**: `parser -> flights -> hotels -> budget -> hotels -> budget -> itinerary`
   (hotels ran twice because of the budget conflict)
2. **BOARD HISTORY**: the `budget delete hotel` line, which is the conflict resolution
3. **RESULT**: the itinerary

With the SQLite board (state is kept in a file):

```bash
python 05-agent-communication/04-shared-blackboard/main.py --offline --sqlite /tmp/trip.db
sqlite3 /tmp/trip.db "select author, op, key from log"
```

## Real LLM

```bash
python 05-agent-communication/04-shared-blackboard/main.py "5 nights in Goa from Mumbai, budget 20000"
python 05-agent-communication/04-shared-blackboard/main.py "Delhi to Goa, 3 nights, 1 lakh budget, luxury"
python 05-agent-communication/04-shared-blackboard/main.py "Delhi to Goa 4 nights with only 2000 rupees"
```

The LLM is used in only two places: parsing the request and writing the itinerary. The other agents are deterministic
(standing in for real APIs). Check whether the LLM understands "1 lakh" as 100000.

## Tests

```bash
pytest 05-agent-communication/04-shared-blackboard -v
```

| Test | What it proves |
|---|---|
| `test_budget_conflict_makes_hotel_agent_retry_cheaper[InMemory/Sqlite]` | conflict → delete + hint → retry; both stores behave the same |
| `test_generous_budget_keeps_best_rated_hotel` | with enough budget, the best-rated choice |
| `test_impossible_request_stops_with_error` | no hotel fits → graceful stop |
| `test_no_route_error` | no flight → error, the controller stops |
| `test_sqlite_board_persists_across_instances` | new object, same file → same state |
| `test_in_memory_board_is_thread_safe` | 8 threads × 200 writes, nothing lost |

## Tinker with it

1. **New agent:** build a `WeatherAgent` that reads `request` and writes `weather`, and let `ItineraryAgent`
   use the weather in the itinerary. Did you have to change the controller or any agent? (No, that is the point.)
2. **LLM controller:** in `Controller`, instead of `ready[0]`, ask an LLM *"here is the board, here are the ready
   agents, who should run?"* (`llm_json` + pydantic). Compare priority vs LLM scheduling.
3. **Parallel:** flights and hotels are independent. Run both together with a `ThreadPoolExecutor`.
   The lock keeps the board safe.
4. **Create a livelock:** remove `rejected_hotels` from `BudgetAgent`. What happens? How does `max_iterations`
   save you?
5. **Resume:** run with `--sqlite`, hit Ctrl+C halfway (or use `max_iterations=3`), then run again from the same
   file. The work should continue from where it stopped (the idea behind checkpointing).
