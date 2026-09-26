**Language:** Hinglish · [English](TESTING.en.md)

# 05 · Event Bus / Pub-Sub: Test aur tinker kaise karein

## Offline demo

```bash
python 05-agent-communication/05-event-bus-pubsub/main.py --offline
```

Output padhne ka tareeka:

- **DELIVERY LOG**: `event_id subscriber outcome`. Order mixed hai, kyunki sab async chal rahe hain.
  - `notify-approved retry 1: gateway timeout` phir `ok`: transient failure, retry ne bacha liya
  - `invalid phone ... retry 1, retry 2, dead-letter`: poison message DLQ mein gaya
- **SMS SENT**: sirf 2 (O-1, O-2). O-1 do baar publish hua tha, phir bhi ek hi SMS gaya (idempotency).
- **ANALYTICS**: `order.created: 3` (4 nahi, duplicate skip hua)
- **DEAD LETTERS**: O-3, attempts=3

## Real LLM

```bash
python 05-agent-communication/05-event-bus-pubsub/main.py
```

Ab fraud decision asli LLM lega. `ORDERS` list (`main.py`) mein apne orders add karke dekho LLM kab
`high` bolta hai. SMS text bhi LLM likhega.

## Tests

```bash
pytest 05-agent-communication/05-event-bus-pubsub -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_fanout_routing_and_wildcard_analytics` | approved/flagged routing, `order.*` wildcard |
| `test_duplicate_publish_is_processed_once` | at-least-once delivery + idempotent consumer |
| `test_transient_failure_is_retried` | 2 fails → 3rd attempt ok, DLQ khaali |
| `test_permanent_failure_goes_to_dead_letter_without_blocking_others` | poison message DLQ mein, baaki orders chalte rahe |
| `test_idempotent_marks_only_after_success` | fail hua event seen mein nahi gaya, retry hua |

## Tinker karo

1. **DLQ replay:** `bus.replay_dead_letters()` banao jo DLQ ke events dobara publish kare (phone fix karke).
   Real ops mein yahi hota hai.
2. **Non-retryable errors:** `ValueError` pe retry mat karo, seedha DLQ. `_worker` mein exception type check karo.
   Log mein `retry 1: invalid phone` wali lines gayab ho jaani chahiye.
3. **Slow consumer:** `AnalyticsAgent.on_any` mein `await asyncio.sleep(1)` daalo. Dekho baaki pipeline
   ruki ya nahi (per-subscriber queue ka faayda).
4. **Backpressure:** `asyncio.Queue(maxsize=2)` karo aur 50 orders publish karo. `publish` ab wait karega.
   Yahi backpressure hai.
5. **Persistence:** bus ko sqlite-backed banao (events table + `status` column), taaki process crash
   ke baad pending events wapas uth sakein. Redis Streams / Kafka yahi durability dete hain.
6. **Event versioning:** `order.created.v2` publish karo naye field ke saath; purana subscriber `order.created`
   pe hai. Dono kaise co-exist karein?
