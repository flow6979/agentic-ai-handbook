**Language:** [Hinglish](CONCEPTS.md) · English

# 01 · Direct Message Passing (Envelopes)

## What is the basic idea?

When two agents live in the same process, the simplest approach is for one agent to
**send a message** to the other. But a "message" should not be just a string. We put it inside
an **envelope**:

```
┌──────────────────────── Envelope ────────────────────────┐
│ id:             2bf2ba06        ← unique id per message   │
│ sender:         summarizer      ← who sent it             │
│ recipient:      translator      ← who it is for           │
│ type:           request         ← request/response/event  │
│ correlation_id: None            ← which request it answers│
│ ts:             1727170000.12   ← when it was sent        │
├───────────────────────────────────────────────────────────┤
│ payload: {"text": "...", "target_lang": "Hindi"}          │
│          ↑ the actual data (the letter inside)            │
└───────────────────────────────────────────────────────────┘
```

**Why?** Because the biggest problem in a multi-agent system is debugging: *"who said what to
whom, and which question was this answer for?"* The envelope metadata lets you trace all of that.

## Two communication styles

### 1) Request / Response (synchronous)

Like a function call: send it and wait until the reply arrives.

```
 user            MessageBus          summarizer          translator
  │  request(id=A)   │                    │                   │
  │─────────────────►│  deliver           │                   │
  │                  │───────────────────►│                   │
  │                  │   request(id=B)    │  (agent→agent)    │
  │                  │◄───────────────────│                   │
  │                  │  deliver                               │
  │                  │───────────────────────────────────────►│
  │                  │   response(corr=B)                     │
  │                  │◄───────────────────────────────────────│
  │                  │───────────────────►│                   │
  │                  │ response(corr=A)   │                   │
  │◄─────────────────│◄───────────────────│                   │
```

`correlation_id` = "this reply belongs to request B". This lets nested calls work without confusion.

### 2) Fire-and-Forget (events)

Send it and forget it. No reply is expected. Used for notifications, logs and analytics.

```
 translator ──event──► [ inbox queue ] ──(drained later)──► audit
                 ↑
          moves on immediately, does not wait
```

| | Request/Response | Fire-and-Forget |
|---|---|---|
| Does the caller wait? | Yes | No |
| Is there a reply? | Yes (with correlation_id) | No |
| Use case | "I need a translation" | "I finished translating" (audit) |
| Do you learn about failures? | Immediately (error envelope) | No (needs separate monitoring) |

## Message types (subtypes)

- **request**: you want something done
- **response**: a successful reply to a request
- **error**: the request failed (agent crash, unknown recipient, validation)
- **event**: something happened, you are just announcing it

## What does the MessageBus (post office) do?

```
           ┌────────────── MessageBus ──────────────┐
 send() ──►│  1. write to the log (tracing)          │
request()─►│  2. find the recipient (registry)       │──► agent.handle()
           │  3. crash? → error envelope             │
           │  4. depth check (prevents ping-pong)    │
           └─────────────────────────────────────────┘
```

Production guards shown here:

1. An **unknown recipient** does not crash; it becomes an error envelope.
2. An **agent exception** also becomes an error envelope; the bus does not go down.
3. **max_depth**: A → B → A → B... infinite loops are a real danger with LLM agents
   (both keep asking each other to "clarify"). Put a depth limit on it.
4. **Log**: every message is recorded. `bus.conversation(id)` pulls out a whole thread.

## When to use it, and when not to

**Use it when:**
- all agents are in the same process/service
- the system is small (2-5 agents) and you need low latency
- you want a simple, debuggable setup

**Do not use it when:**
- agents are on different machines/services → HTTP (project 06) or A2A (08)
- many consumers listen to one event → pub/sub (project 05)
- agents need to collaborate on shared state → blackboard (project 04)

## Common pitfalls

- **Sending free text in the payload** → the receiver cannot parse it. Keep the payload a dict/schema.
- **Forgetting the correlation_id** → in an async world, responses cannot be matched.
- **Errors vanish in fire-and-forget** → you need a dead-letter queue / monitoring (see project 05).
- **No cycle detection** → token bills and infinite loops.

## How this project uses it

| Concept | File / function |
|---|---|
| Envelope + `reply()` (sets the correlation id) | `dm_bus.py` → `Envelope` |
| Post office, registry, log, depth guard | `dm_bus.py` → `MessageBus.request / send / drain` |
| Agent → agent call | `dm_bus.py` → `BusAgent.ask()` (request), `BusAgent.tell()` (event) |
| LLM translator | `dm_agents.py` → `TranslatorAgent` |
| Summarizer that calls the translator itself | `dm_agents.py` → `SummarizerAgent.handle` |
| Fire-and-forget consumer | `dm_agents.py` → `AuditLogAgent` |
| Demo + message log print | `main.py` |

Flow:

```
user ─request─► summarizer ──LLM──► summary
                    │
                    ├─request─► translator ──LLM──► translation
                    │               └─event─► audit (queued)
                    └─event─► audit (queued)
bus.drain() → audit receives both events
```
