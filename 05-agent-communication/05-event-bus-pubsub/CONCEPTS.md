**Language:** Hinglish · [English](CONCEPTS.en.md)

# 05 · Event Bus / Pub-Sub (Async, decoupled agents)

## Basic idea

Ab tak (01, 02, 03) sender ko pata hota tha ki **kisko** bhejna hai. Pub/Sub mein aisa nahi hai:

- **Publisher** bolta hai: *"order.created hua hai"* (topic pe event daala)
- **Subscribers** ne pehle se bola hua hai: *"mujhe order.created chahiye"*
- **Bus** beech mein hai aur har matching subscriber tak copy pahunchata hai

Publisher ko pata hi nahi kaun sun raha hai. Yeh sabse **loosely coupled** communication hai.

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

**Har subscriber ki apni queue + worker** hai. Agar Notification slow hai (SMS gateway down),
FraudCheck aur Analytics chalte rehte hain. Kafka mein isko **consumer group** kehte hain.

## Poora order flow (sequence)

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

## Delivery guarantees (sabse important concept)

| Guarantee | Matlab | Problem |
|---|---|---|
| **At-most-once** | Ek baar bhejo, fail hua to gaya | Events kho sakte hain |
| **At-least-once** (yeh project) | Fail pe retry, jab tak success ya DLQ | **Duplicates** aa sakte hain |
| **Exactly-once** | Na kho, na duplicate | Bahut mushkil/mehenga; practically "at-least-once + idempotency" |

### Idempotency: duplicates se kaise bachein

Duplicates do jagah se aate hain:
1. **Producer retry**: checkout ne publish kiya, network glitch, "shayad nahi gaya", phir se publish
2. **Consumer retry**: handler ne kaam kar diya, lekin ack se pehle crash, to bus dobara deliver karta hai

**Solution:** har event pe **idempotency key** (business key, e.g. `"O-1:created"`), aur consumer
yaad rakhe ki kaunsi keys process ho chuki hain.

```
 event(key=O-1:created) ──► seen mein hai? ──haan──► skip (kuch mat karo)
                                 │ nahi
                                 ▼
                           handler chalao ──success──► seen.add(key)
                                 │ fail
                                 ▼
                           seen mein MAT daalo (warna retry skip ho jayega!)
```

At-least-once + idempotent consumer = **effectively once**. Industry mein yahi practical pattern hai.

## Retry, backoff aur Dead Letter Queue (DLQ)

```
 attempt 1 ✗ ──sleep 1×──► attempt 2 ✗ ──sleep 2×──► attempt 3 ✗ ──► DEAD LETTER
                                                         (max_attempts=3)
```

- **Exponential backoff**: har retry ke beech wait double. Down service pe load nahi daalte.
- **DLQ**: jo events kabhi process nahi ho sakte (invalid phone), unko alag rakh do. Queue block
  nahi hoti, aur baad mein koi insaan/job inko dekh ke fix + replay kar sakta hai.
- **Poison message**: aisa event jo hamesha fail hoga. Bina DLQ ke yeh queue ko hamesha ke liye atka deta hai.

## Real brokers se mapping

| Is project mein | Redis Streams | Kafka | RabbitMQ | AWS SQS/SNS |
|---|---|---|---|---|
| `EventBus` | Redis server | Kafka cluster | Broker | SNS + SQS |
| topic `order.created` | stream key | topic | exchange + routing key | SNS topic |
| wildcard `order.*` | (khud filter) | regex subscribe | topic exchange `order.*` | filter policy |
| per-subscriber queue | consumer group | consumer group | queue bound to exchange | SQS queue per subscriber |
| `queue.task_done()` | `XACK` | offset commit | `basic.ack` | `DeleteMessage` |
| retry | pending entries + `XCLAIM` | re-consume (offset commit nahi hua) | `nack` + requeue | visibility timeout |
| `dead_letters` | alag stream | DLQ topic | dead-letter exchange | redrive policy → DLQ |
| `idempotent()` seen set | Redis SET + TTL | DB unique key | DB unique key | DB unique key |

## Pub/Sub vs baaki styles

| | Direct (01) | Blackboard (04) | Pub/Sub (05) |
|---|---|---|---|
| Sender ko recipient pata? | Haan | Nahi | Nahi |
| Sync/async | Sync | Loop pe depend | Async |
| Naya consumer add karna | Sender badlo | Controller mein daalo | Bas subscribe karo |
| Order guarantee | Haan | Controller decide karta | Per-queue order, global nahi |
| Best for | Chhota, request/response | Incremental problem solving | Events, pipelines, fan-out, scale |

## Kab use karein / kab nahi

**Use karo:** ek event pe kai independent reactions, spikes absorb karne hain (queue buffer),
services alag teams/machines pe hain, ya failure isolation chahiye.

**Mat use karo:** turant jawab chahiye (user wait kar raha hai) → request/response lo. Strict
global ordering chahiye → single partition/queue ya alag design. Debugging bhi mushkil hai: flow
code mein nahi dikhta, isliye tracing (event ids, log) zaroori hai.

## Pitfalls

- **Idempotency bhoolna** → double SMS, double refund
- **Seen mark karna handler se pehle** → fail hua event retry pe skip ho jaata hai
- **Permanent errors ko bhi retry karna** (invalid phone) → waste. Retryable vs non-retryable alag karo (Tinker #2)
- **Blocking LLM call event loop mein** → saare agents ruk jaate hain → `asyncio.to_thread`
- **Event schema change** → purane consumers toot jaate hain → version field (`order.created.v2`)

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Event (id, topic, idempotency_key, attempts) | `pubsub_bus.py` → `Event` |
| Topics, wildcard, per-subscriber queue + worker | `EventBus.subscribe / publish / _worker` |
| Retry + exponential backoff + DLQ | `EventBus._worker` |
| Wait till all queues drain | `EventBus.wait_idle` |
| Idempotent consumer (mark after success) | `pubsub_bus.py` → `idempotent()` |
| LLM fraud check → publishes next event | `pubsub_orders.py` → `FraudCheckAgent` (`llm_json`, `asyncio.to_thread`) |
| Flaky dependency | `SmsGateway(fail_times=…)`, `000…` phone = poison message |
| Wiring (who subscribes to what) | `pubsub_orders.py` → `wire()` |
| Producer retry duplicate | `main.py` (O-1 do baar publish) |
