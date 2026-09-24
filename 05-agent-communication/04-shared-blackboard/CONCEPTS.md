# 04 · Shared Blackboard (Shared state pe collaboration)

## Basic idea

Socho ek classroom mein ek **whiteboard** hai. Alag-alag experts (flight expert, hotel expert,
budget expert) board ke saamne khade hain. Koi kisi se baat nahi karta. Har expert board
dekhta hai: *"kya yahan kuch hai jisme main value add kar sakta hoon?"* Haan hai, to woh apna
hissa board pe likh deta hai. Phir baaki log naya likha hua dekh ke apna kaam karte hain.

Yahi **Blackboard Architecture** hai (1970s ka AI pattern, Hearsay-II speech system se).
Aaj ke multi-agent systems mein iska naam **"shared state"** hai (LangGraph ka `State`
yahi concept hai).

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
                        │ "abhi kaun chalega?"
                  ┌─────┴──────┐
                  │ CONTROLLER │
                  └────────────┘
```

## Teen hisse

1. **Blackboard**: shared data store (key → value) + history (kisne kab kya likha)
2. **Knowledge Sources (agents)**: har ek ke do methods:
   - `can_contribute(board)`: kya board ki current state pe main kuch kar sakta hoon?
   - `contribute(board)`: apna kaam karke board update karo
3. **Controller**: loop jo decide karta hai ki abhi kaun chalega, aur kab rukna hai

## Controller loop

```
 ┌─► goal (itinerary) board pe hai? ──haan──► STOP ✓
 │         │ nahi
 │         ▼
 │   error hai? ──haan──► STOP ✗
 │         │ nahi
 │         ▼
 │   ready = [agents jinka can_contribute() == True]
 │         │
 │   ready khaali? ──haan──► STOP (deadlock: koi aage nahi badh sakta)
 │         │ nahi
 │         ▼
 │   pehla ready agent chalao (priority order)
 └─────────┘   (max_iterations guard ke saath)
```

## Conflict resolution: budget toot gaya to kya?

Yeh blackboard ki sabse khoobsurat cheez hai: **agents ek dusre ka kaam "undo" karke hint chhod sakte hain**.

```
 hotels:  hotel = Taj (9000/night, rating 4.8)
 budget:  7800 + 9000×4 = 43800 > 25000 ✗
          → rejected_hotels += Taj
          → hotel_hint = "cheaper"
          → DELETE hotel
 hotels:  can_contribute? "hotel" key nahi hai → haan!
          hint = cheaper → Taj se saste mein best-rated → Sea Breeze (3500)
 budget:  7800 + 3500×4 = 21800 ≤ 25000 ✓ → budget_ok
 itinerary: ab chal sakta hai
```

Kisi agent ne kisi ko "call" nahi kiya. Sab board ke through hua.

## Implementations (subtypes of the store)

| Store | Kab |
|---|---|
| `InMemoryBlackboard` (dict + Lock) | ek process, threads safe |
| `SqliteBlackboard` | restart ke baad state bachi rahe, ya multiple processes ek file share karein |
| Redis hash / Postgres (real world) | distributed agents, multiple machines |
| LangGraph `State` + checkpointer | graph-based agents, time-travel debugging |

**Lock kyun?** Do agent threads ek saath likhein to race condition ho sakti hai. `threading.Lock`
ya DB transaction se ek waqt pe ek hi likhta hai.

## Scheduling policies (controller ke variants)

- **Priority order** (yeh project): list mein pehla ready agent
- **Opportunistic**: har ready agent ek round mein
- **LLM-controller**: ek LLM board dekh ke decide kare kaun chalega (supervisor jaisa)
- **Parallel**: saare ready agents threads mein ek saath (lock zaroori)

## Blackboard vs Message passing

| | Message passing (01) | Blackboard (04) |
|---|---|---|
| Coupling | Sender ko recipient ka naam pata hona chahiye | Koi kisi ko nahi jaanta, sirf board keys |
| Naya agent add karna | Callers badalne padte hain | Sirf list mein daal do |
| State kahan | Messages mein bikhri hui | Ek jagah, poora snapshot |
| Debugging | Message log | Board history (who/when/what) |
| Risk | Chatty, cycles | Board schema pe sabki dependency, contention |

## Kab use karein / kab nahi

**Use karo:** problem incrementally solve hoti hai, kai specialists partial results jodte hain,
order pehle se fixed nahi (conflicts/retries aate hain), ya tumhe poora state ek jagah chahiye.

**Mat use karo:** simple linear pipeline hai (seedha chain lo), ya bahut high-frequency writes
hain (contention).

## Pitfalls

- **Key naming chaos**: board ka schema document karo (yahan `blackboard_trip.py` ke top pe hai)
- **Deadlock**: koi agent ready nahi, goal bhi nahi → controller detect karke ruke
- **Livelock**: A likhe, B mitaye, A phir likhe... → `max_iterations` aur `rejected_*` memory
- **Bina history ke debugging** → har write ka author + timestamp rakho

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Blackboard interface + 2 stores | `blackboard_store.py` |
| Thread safety (Lock), transactions (sqlite) | `InMemoryBlackboard`, `SqliteBlackboard.set` |
| Audit trail | `history()` |
| Knowledge sources | `blackboard_trip.py` → `RequestParser` (LLM), `FlightAgent`, `HotelAgent`, `BudgetAgent`, `ItineraryAgent` (LLM) |
| Structured LLM output board pe | `RequestParser` → `llm_json(..., TripRequest)` |
| Conflict resolution (delete + hint) | `BudgetAgent.contribute` |
| Controller loop, deadlock/goal/max_iter | `Controller.run` |
