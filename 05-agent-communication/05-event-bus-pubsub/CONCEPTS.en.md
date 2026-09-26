**Language:** [Hinglish](CONCEPTS.md) · English

# 05 · Event Bus / Pub-Sub (async, decoupled agents)

## Basic idea

So far (01, 02, 03) the sender knew **whom** to send to. Pub/Sub does not work that way:

- The **publisher** says: *"order.created happened"* (puts an event on a topic)
- The **subscribers** have said in advance: *"I want order.created"*
- The **bus** sits in the middle and delivers a copy to every matching subscriber

The publisher has no idea who is listening. This is the most **loosely coupled** form of communication.

```
                          ┌───────────────── EVENT BUS ─────────────────┐
 checkout ──publish──►    │ topic: order.created                        │
 "order.created"          │    ├──► [queue: fraud]      ──► FraudCheck  │──► publish order.approved / order.flagged
                          │    └──► [queue: analytics]  ──► Analytics   │
                          │ topic: order.approved                       │
                          │    ├──► [queue: notify-approved] ──► Notify │──► SMS
                          │    └──► [queue: analytics]                  │
                          │ topic: order.flagged                        │
                          │    ├──► [queue: notify-flagged]  ──► Notify │
                          │    └──► [queue: analytics]  (pattern order.*)│
                          └─────────────────────────────────────────────┘
```

**Every subscriber has its own queue + worker.** If Notification is slow (the SMS gateway is down),
FraudCheck and Analytics keep running. In Kafka this is called a **consumer group**.

## The full order flow (sequence)

```
 checkout      Bus        Fraud(LLM)     Notify(LLM)     SMS gw      Analytics
    │ created   │              │              │             │            │
    │──────────►│─────────────►│              │             │            │
    │           │──────────────────────────────────────────────────────►│ count
    │           │   approved   │ llm_json     │             │            │
    │           │◄─────────────│ risk=low     │             │            │
    │           │─────────────────────────────►│ LLM sms    │            │
    │           │                             │────────────►│ ✗ timeout  │
    │           │   (retry, backoff)          │────────────►│ ✓ sent     │
    │           │──────────────────────────────────────────────────────►│ count
```

## Delivery guarantees (the most important concept)

| Guarantee | Meaning | Problem |
|---|---|---|
| **At-most-once** | Send once; if it fails, it is gone | Events can be lost |
| **At-least-once** (this project) | Retry on failure until success or DLQ | **Duplicates** can arrive |
| **Exactly-once** | Never lost, never duplicated | Very hard/expensive; in practice "at-least-once + idempotency" |

### Idempotency: how to survive duplicates

Duplicates come from two places:
1. **Producer retry**: checkout published, a network glitch happened, "maybe it did not go through", so it publishes again
2. **Consumer retry**: the handler did the work but crashed before the ack, so the bus delivers again

**Solution:** put an **idempotency key** on every event (a business key, e.g. `"O-1:created"`), and have the consumer
remember which keys it has already processed.

```
 event(key=O-1:created) ──► already in seen? ──yes──► skip (do nothing)
                                 │ no
                                 ▼
                           run the handler ──success──► seen.add(key)
                                 │ fail
                                 ▼
                           do NOT add it to seen (otherwise the retry gets skipped!)
```

At-least-once + an idempotent consumer = **effectively once**. This is the practical pattern in industry.

## Retry, backoff and the Dead Letter Queue (DLQ)

```
 attempt 1 ✗ ──sleep 1×──► attempt 2 ✗ ──sleep 2×──► attempt 3 ✗ ──► DEAD LETTER
                                                         (max_attempts=3)
```

- **Exponential backoff**: the wait doubles between retries, so you do not pile load onto a service that is down.
- **DLQ**: events that can never be processed (an invalid phone number) are put aside. The queue does not
  get blocked, and later a person/job can inspect them, fix them and replay them.
- **Poison message**: an event that will always fail. Without a DLQ it blocks the queue forever.

## Mapping to real brokers

| In this project | Redis Streams | Kafka | RabbitMQ | AWS SQS/SNS |
|---|---|---|---|---|
| `EventBus` | Redis server | Kafka cluster | Broker | SNS + SQS |
| topic `order.created` | stream key | topic | exchange + routing key | SNS topic |
| wildcard `order.*` | (filter yourself) | regex subscribe | topic exchange `order.*` | filter policy |
| per-subscriber queue | consumer group | consumer group | queue bound to exchange | SQS queue per subscriber |
| `queue.task_done()` | `XACK` | offset commit | `basic.ack` | `DeleteMessage` |
| retry | pending entries + `XCLAIM` | re-consume (offset was not committed) | `nack` + requeue | visibility timeout |
| `dead_letters` | separate stream | DLQ topic | dead-letter exchange | redrive policy → DLQ |
| `idempotent()` seen set | Redis SET + TTL | DB unique key | DB unique key | DB unique key |

## Pub/Sub vs the other styles

| | Direct (01) | Blackboard (04) | Pub/Sub (05) |
|---|---|---|---|
| Does the sender know the recipient? | Yes | No | No |
| Sync/async | Sync | Depends on the loop | Async |
| Adding a new consumer | Change the sender | Add it to the controller | Just subscribe |
| Ordering guarantee | Yes | The controller decides | Per-queue order, not global |
| Best for | Small, request/response | Incremental problem solving | Events, pipelines, fan-out, scale |

## When to use it / when not to

**Use it:** when one event triggers several independent reactions, you need to absorb spikes (the queue buffers),
services live on different teams/machines, or you need failure isolation.

**Do not use it:** when you need an immediate reply (the user is waiting) → use request/response. When you need strict
global ordering → a single partition/queue or a different design. Debugging is also harder: the flow is not
visible in the code, so tracing (event ids, logs) is essential.

## Pitfalls

- **Forgetting idempotency** → double SMS, double refunds
- **Marking as seen before the handler runs** → a failed event gets skipped on retry
- **Retrying permanent errors too** (invalid phone) → waste. Separate retryable vs non-retryable (Tinker #2)
- **A blocking LLM call inside the event loop** → every agent stalls → `asyncio.to_thread`
- **Event schema changes** → old consumers break → a version field (`order.created.v2`)

## How this project uses it

| Concept | Where |
|---|---|
| Event (id, topic, idempotency_key, attempts) | `pubsub_bus.py` → `Event` |
| Topics, wildcard, per-subscriber queue + worker | `EventBus.subscribe / publish / _worker` |
| Retry + exponential backoff + DLQ | `EventBus._worker` |
| Wait until all queues drain | `EventBus.wait_idle` |
| Idempotent consumer (mark after success) | `pubsub_bus.py` → `idempotent()` |
| LLM fraud check → publishes the next event | `pubsub_orders.py` → `FraudCheckAgent` (`llm_json`, `asyncio.to_thread`) |
| Flaky dependency | `SmsGateway(fail_times=…)`, a `000…` phone = poison message |
| Wiring (who subscribes to what) | `pubsub_orders.py` → `wire()` |
| Producer retry duplicate | `main.py` (O-1 published twice) |
