**Language:** [Hinglish](TESTING.md) · English

# 05 · Event Bus / Pub-Sub: how to test and tinker

## Offline demo

```bash
python 05-agent-communication/05-event-bus-pubsub/main.py --offline
```

How to read the output:

- **DELIVERY LOG**: `event_id subscriber outcome`. The order is mixed because everything runs async.
  - `notify-approved retry 1: gateway timeout` then `ok`: a transient failure, saved by the retry
  - `invalid phone ... retry 1, retry 2, dead-letter`: a poison message went to the DLQ
- **SMS SENT**: only 2 (O-1, O-2). O-1 was published twice, yet only one SMS went out (idempotency).
- **ANALYTICS**: `order.created: 3` (not 4, the duplicate was skipped)
- **DEAD LETTERS**: O-3, attempts=3

## Real LLM

```bash
python 05-agent-communication/05-event-bus-pubsub/main.py
```

Now a real LLM makes the fraud decision. Add your own orders to the `ORDERS` list (`main.py`) and see when the LLM
says `high`. The LLM also writes the SMS text.

## Tests

```bash
pytest 05-agent-communication/05-event-bus-pubsub -v
```

| Test | What it proves |
|---|---|
| `test_fanout_routing_and_wildcard_analytics` | approved/flagged routing, the `order.*` wildcard |
| `test_duplicate_publish_is_processed_once` | at-least-once delivery + idempotent consumer |
| `test_transient_failure_is_retried` | 2 failures → 3rd attempt ok, DLQ empty |
| `test_permanent_failure_goes_to_dead_letter_without_blocking_others` | the poison message lands in the DLQ, the other orders keep flowing |
| `test_idempotent_marks_only_after_success` | a failed event was not added to seen, so it was retried |

## Tinker with it

1. **DLQ replay:** build `bus.replay_dead_letters()` that republishes the DLQ's events (after fixing the phone).
   This is exactly what happens in real ops.
2. **Non-retryable errors:** do not retry on `ValueError`, send it straight to the DLQ. Check the exception type in `_worker`.
   The `retry 1: invalid phone` lines should disappear from the log.
3. **Slow consumer:** put `await asyncio.sleep(1)` in `AnalyticsAgent.on_any`. See whether the rest of the pipeline
   stalls (the benefit of per-subscriber queues).
4. **Backpressure:** use `asyncio.Queue(maxsize=2)` and publish 50 orders. `publish` will now wait.
   That is backpressure.
5. **Persistence:** make the bus sqlite-backed (an events table + a `status` column), so pending events can be picked
   up again after a process crash. Redis Streams / Kafka give you exactly this durability.
6. **Event versioning:** publish `order.created.v2` with a new field; the old subscriber is on `order.created`.
   How do both co-exist?
