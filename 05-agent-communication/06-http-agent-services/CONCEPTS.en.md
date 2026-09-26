**Language:** [Hinglish](CONCEPTS.md) · English

# 06 · Agents as HTTP Microservices

## Basic idea

Until now every agent lived in **one process**. In real companies:
- the summarizer agent was built by one team, in Python, on one server
- the sentiment agent belongs to another team, maybe in a different language/model
- the orchestrator lives somewhere else again

For these to talk they need a **network**. The most common approach: **HTTP + JSON (REST)**.
Every agent becomes a **microservice**.

```
                         ┌───────────────────────┐
                         │  REGISTRY  :8000      │  "who is where, what can they do"
                         │  summarizer → :8001   │
                         │  sentiment  → :8002   │
                         └───▲───────────▲───────┘
            1. register      │           │  2. GET /agents?skill=summarize
     (by itself on startup)  │           │
┌──────────────────┐         │     ┌─────┴─────────────┐
│ summarizer :8001 │─────────┘     │   ORCHESTRATOR    │
│ POST /invoke     │◄──────────────│   (LLM agent)     │
│ POST /jobs       │ 3. POST /invoke│ tool:             │
└──────────────────┘   + Bearer    │ call_remote_agent │
┌──────────────────┐               │                   │
│ sentiment  :8002 │◄──────────────│                   │
└──────────────────┘               └───────────────────┘
```

## Every agent service's "contract" (endpoints)

| Endpoint | Job |
|---|---|
| `GET /health` | Is it alive? (load balancer, Kubernetes probe) |
| `GET /info` | Name + skills (self-description) |
| `POST /invoke {input}` | **Sync**: the answer comes in this same response |
| `POST /jobs {input, callback_url?}` | **Async**: immediate `202 + job_id` |
| `GET /jobs/{id}` | Job status: `queued → running → done/failed` |

## Sync vs async (the most important design choice)

### Sync (request/response)

```
 client ──POST /invoke──► agent ──(LLM 3s)──► 200 {output}
        ◄───────────────────────────────────────┘
   (the client sat there holding the connection open for 3 seconds)
```

Fine for small jobs. But what if the LLM work takes 2 minutes? HTTP timeouts, load balancer
timeouts (often 60s), and holding a connection open is wasteful.

### Async job pattern (poll or webhook)

```
 client ──POST /jobs──────────► agent: job created, 202 {job_id} immediately
        ◄── 202 {job_id} ──────┘   │
                                   ├─ LLM work in the background...
 client ──GET /jobs/abc──► {status: running}
 client ──GET /jobs/abc──► {status: done, output}        ← (A) POLLING
                                   │
                                   └─POST callback_url {job_id, output} ──► client  ← (B) WEBHOOK
```

| | Polling | Webhook (callback) |
|---|---|---|
| How | The client keeps asking | The server tells you itself |
| Does the client need a public URL? | No | Yes |
| Waste | Extra requests | Less |
| Reliability | Simple | The webhook can fail → keep polling as a fallback |

This project has both, and even if the webhook fails you can still get the result from `/jobs/{id}`.

## Rules for talking over a network (resilience)

```
 AgentClient._request:
   for attempt in 0..retries:
       try: response = http(...)            ← ALWAYS a TIMEOUT
            5xx?  → retry (server problem, maybe temporary)
            4xx?  → do NOT retry (your mistake: auth/validation)
            ok    → return
       except timeout / connection error → retry
       sleep(backoff × 2^attempt)            ← exponential backoff
   give up → RemoteAgentError
```

1. **Timeout**: without a timeout, one stuck service stalls the whole system
2. **Retry only on safe errors**: retry a 503, not a 401
3. **Backoff**: do not hammer a service that is down
4. **Idempotency**: retrying a POST can duplicate work (the job gets created twice). In real systems
   send an `Idempotency-Key` header (the concept from project 05)
5. **Auth**: `Authorization: Bearer <token>`. Here it is a shared secret; in production use OAuth2/JWT/mTLS

## Service discovery

Do not hardcode URLs in the orchestrator. Look them up in a **registry** by skill:

```
 client.invoke_skill("summarize", text)
    → GET registry/agents?skill=summarize → [{"url": "http://127.0.0.1:8001"}]
    → POST http://127.0.0.1:8001/invoke
```

Real world: Kubernetes DNS (`http://summarizer.svc`), Consul, Eureka.

## How does this lead to the A2A protocol?

In this project we built **our own protocol**: our own endpoints, our own JSON shape, our own registry.
The problem: if every company invents its own protocol, Company A's agent simply cannot talk to
Company B's agent.

```
 Ours:     /info          /invoke {input}     /jobs + /jobs/{id}    custom registry
 A2A:      Agent Card     message/send        tasks (states) +      /.well-known/agent.json
           (skills, auth) (JSON-RPC)          streaming / push      discovery
```

**A2A (Agent2Agent)** **standardizes** exactly these things: discovery (Agent Card),
message format, task lifecycle (submitted/working/completed/failed), streaming (SSE),
push notifications (webhooks), and auth schemes. That is why any vendor's agent can talk to any other's.
`08-a2a/` implements it. Once you understand this project, A2A will feel like just
"the standard version of this".

## When to use it / when not to

**Use it:** when agents live on different teams/languages/machines, need to be deployed/scaled independently,
or sit behind different security boundaries.

**Do not use it:** when everything is in one small codebase → in-process (01/02) is simpler and faster.
Network = the burden of latency + failures + auth + versioning.

## Pitfalls

- Not setting a timeout, or giving every layer the same timeout (the orchestrator's should be larger)
- Retrying on 4xx
- Dead agents in the registry: you need a heartbeat/TTL (Tinker #3)
- Sensitive data over plaintext HTTP → HTTPS
- Background jobs kept in process memory → gone on restart (in real systems keep them in a DB/queue)

## How this project uses it

| Concept | Where |
|---|---|
| Agent service endpoints, auth dependency | `httpsvc_service.py` → `create_agent_app` |
| Async job (BackgroundTasks) + webhook | `httpsvc_service.py` → `submit`, `_run_job`, `callback_poster` |
| Self-registration on startup | `httpsvc_service.py` → `lifespan` |
| Registry / discovery | `httpsvc_registry.py` |
| Timeout, retry, backoff, 4xx vs 5xx | `httpsvc_client.py` → `AgentClient._request` |
| Poll until done | `AgentClient.wait_for_job` |
| Remote agents as LLM tools | `httpsvc_agents.py` → `build_orchestrator` |
| Multi-terminal real run, offline in-process run | `main.py` |
