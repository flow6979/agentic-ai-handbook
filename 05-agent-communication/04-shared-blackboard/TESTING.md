**Language:** Hinglish · [English](TESTING.en.md)

# 04 · Shared Blackboard: Test aur tinker kaise karein

## Offline demo

```bash
python 05-agent-communication/04-shared-blackboard/main.py --offline
```

Teen cheezein dekho:
1. **WHO RAN**: `parser -> flights -> hotels -> budget -> hotels -> budget -> itinerary`
   (hotels do baar chala: budget conflict ki wajah se)
2. **BOARD HISTORY**: `budget delete hotel` line, conflict resolution yahi hai
3. **RESULT**: itinerary

SQLite board ke saath (state file mein bachi rehti hai):

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

LLM sirf do jagah hai: request parse karna aur itinerary likhna. Baaki agents deterministic
hain (real APIs ki jagah). Dekho LLM "1 lakh" ko 100000 samajhta hai ya nahi.

## Tests

```bash
pytest 05-agent-communication/04-shared-blackboard -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_budget_conflict_makes_hotel_agent_retry_cheaper[InMemory/Sqlite]` | conflict → delete + hint → retry; dono stores same behave karte hain |
| `test_generous_budget_keeps_best_rated_hotel` | budget ho to best-rated choice |
| `test_impossible_request_stops_with_error` | koi hotel fit nahi → graceful stop |
| `test_no_route_error` | flight nahi → error, controller ruk jaata hai |
| `test_sqlite_board_persists_across_instances` | naya object, same file → same state |
| `test_in_memory_board_is_thread_safe` | 8 threads × 200 writes, kuch lost nahi |

## Tinker karo

1. **Naya agent:** `WeatherAgent` banao jo `request` dekh ke `weather` likhe, aur `ItineraryAgent`
   ko itinerary mein weather use karne do. Controller ya kisi agent ko badalna pada? (Nahi, yahi point hai.)
2. **LLM controller:** `Controller` mein `ready[0]` ki jagah LLM se poocho *"board yeh hai, ready
   agents yeh hain, kaun chale?"* (`llm_json` + pydantic). Priority vs LLM scheduling compare karo.
3. **Parallel:** flights aur hotels independent hain. Dono ko `ThreadPoolExecutor` se ek saath
   chalao. Lock ki wajah se board safe rahega.
4. **Livelock banao:** `BudgetAgent` se `rejected_hotels` hata do. Kya hota hai? `max_iterations`
   kaise bachata hai?
5. **Resume:** `--sqlite` ke saath chalao, beech mein Ctrl+C (ya `max_iterations=3`), phir wahi file
   se dobara run karo. Kaam wahi se continue hona chahiye (checkpointing ka idea).
