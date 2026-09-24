# 06 · Agents as HTTP Microservices

## Basic idea

Ab tak saare agents **ek hi process** mein the. Real companies mein:
- summarizer agent ek team ne banaya, Python mein, ek server pe
- sentiment agent dusri team ka, shayad alag language/model
- orchestrator kisi teesri jagah

Inko baat karne ke liye **network** chahiye. Sabse common tareeka: **HTTP + JSON (REST)**.
Har agent ek **microservice** ban jaata hai.

```
                         ┌───────────────────────┐
                         │  REGISTRY  :8000      │  "kaun kahan hai, kya kar sakta hai"
                         │  summarizer → :8001   │
                         │  sentiment  → :8002   │
                         └───▲───────────▲───────┘
            1. register      │           │  2. GET /agents?skill=summarize
     (startup pe khud)       │           │
┌──────────────────┐         │     ┌─────┴─────────────┐
│ summarizer :8001 │─────────┘     │   ORCHESTRATOR    │
│ POST /invoke     │◄──────────────│   (LLM agent)     │
│ POST /jobs       │ 3. POST /invoke│ tool:             │
└──────────────────┘   + Bearer    │ call_remote_agent │
┌──────────────────┐               │                   │
│ sentiment  :8002 │◄──────────────│                   │
└──────────────────┘               └───────────────────┘
```

## Har agent service ka "contract" (endpoints)

| Endpoint | Kaam |
|---|---|
| `GET /health` | Zinda hai? (load balancer, Kubernetes probe) |
| `GET /info` | Naam + skills (self-description) |
| `POST /invoke {input}` | **Sync**: jawab isi response mein |
| `POST /jobs {input, callback_url?}` | **Async**: turant `202 + job_id` |
| `GET /jobs/{id}` | Job ka status: `queued → running → done/failed` |

## Sync vs Async (sabse important design choice)

### Sync (request/response)

```
 client ──POST /invoke──► agent ──(LLM 3s)──► 200 {output}
        ◄───────────────────────────────────────┘
   (client 3 second tak connection khol ke baitha raha)
```

Chhote kaam ke liye theek hai. Lekin LLM kaam 2 minute le to? HTTP timeout, load balancer
timeout (often 60s), aur connection pakde rehna waste hai.

### Async job pattern (poll ya webhook)

```
 client ──POST /jobs──────────► agent: job banaya, 202 {job_id} turant
        ◄── 202 {job_id} ──────┘   │
                                   ├─ background mein LLM kaam...
 client ──GET /jobs/abc──► {status: running}
 client ──GET /jobs/abc──► {status: done, output}        ← (A) POLLING
                                   │
                                   └─POST callback_url {job_id, output} ──► client  ← (B) WEBHOOK
```

| | Polling | Webhook (callback) |
|---|---|---|
| Kaise | Client baar baar poochta hai | Server khud batata hai |
| Client ko public URL chahiye? | Nahi | Haan |
| Waste | Extra requests | Kam |
| Reliability | Simple | Webhook fail ho sakta hai → poll fallback rakho |

Is project mein dono hain, aur webhook fail ho to bhi `/jobs/{id}` se result milta hai.

## Network pe baat karne ke niyam (resilience)

```
 AgentClient._request:
   for attempt in 0..retries:
       try: response = http(...)            ← TIMEOUT hamesha
            5xx?  → retry karo (server ki problem, shayad temporary)
            4xx?  → retry MAT karo (tumhari galti: auth/validation)
            ok    → return
       except timeout / connection error → retry
       sleep(backoff × 2^attempt)            ← exponential backoff
   give up → RemoteAgentError
```

1. **Timeout**: bina timeout ek atki service poore system ko atka deti hai
2. **Retry sirf safe errors pe**: 503 retry karo, 401 nahi
3. **Backoff**: down service pe hathoda mat maaro
4. **Idempotency**: POST retry se duplicate kaam ho sakta hai (job do baar bana). Real mein
   `Idempotency-Key` header bhejo (project 05 ka concept)
5. **Auth**: `Authorization: Bearer <token>`. Yahan shared secret hai; production mein OAuth2/JWT/mTLS

## Service discovery

Orchestrator mein URLs hardcode mat karo. **Registry** se skill ke basis pe dhoondho:

```
 client.invoke_skill("summarize", text)
    → GET registry/agents?skill=summarize → [{"url": "http://127.0.0.1:8001"}]
    → POST http://127.0.0.1:8001/invoke
```

Real world: Kubernetes DNS (`http://summarizer.svc`), Consul, Eureka.

## Yeh A2A protocol tak kaise le jaata hai?

Is project mein humne **khud ka protocol** banaya: apne endpoints, apna JSON shape, apni registry.
Problem: agar har company apna protocol banaye, to Company A ka agent Company B ke agent se
baat hi nahi kar sakta.

```
 Humara:   /info          /invoke {input}     /jobs + /jobs/{id}    custom registry
 A2A:      Agent Card     message/send        tasks (states) +      /.well-known/agent.json
           (skills, auth) (JSON-RPC)          streaming / push      discovery
```

**A2A (Agent2Agent)** exactly yahi cheezein **standardize** karta hai: discovery (Agent Card),
message format, task lifecycle (submitted/working/completed/failed), streaming (SSE),
push notifications (webhooks), aur auth schemes. Isliye kisi bhi vendor ka agent kisi aur se
baat kar sakta hai. `08-a2a/` mein woh implement hai. Is project ko samajh lo, to A2A bas
"inka standard version" lagega.

## Kab use karein / kab nahi

**Use karo:** agents alag teams/languages/machines pe hain, independently deploy/scale karne hain,
ya alag security boundaries hain.

**Mat use karo:** sab ek hi codebase mein hai aur chhota hai → in-process (01/02) simple aur fast hai.
Network = latency + failures + auth + versioning ka bojh.

## Pitfalls

- Timeout na lagana, ya har layer ka timeout same rakhna (orchestrator ka bada hona chahiye)
- 4xx pe retry
- Registry mein dead agents: heartbeat/TTL chahiye (Tinker #3)
- Sensitive data plaintext HTTP pe → HTTPS
- Background jobs process memory mein → restart pe gayab (real mein DB/queue mein rakho)

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Agent service endpoints, auth dependency | `httpsvc_service.py` → `create_agent_app` |
| Async job (BackgroundTasks) + webhook | `httpsvc_service.py` → `submit`, `_run_job`, `callback_poster` |
| Self-registration on startup | `httpsvc_service.py` → `lifespan` |
| Registry / discovery | `httpsvc_registry.py` |
| Timeout, retry, backoff, 4xx vs 5xx | `httpsvc_client.py` → `AgentClient._request` |
| Poll until done | `AgentClient.wait_for_job` |
| Remote agents as LLM tools | `httpsvc_agents.py` → `build_orchestrator` |
| Multi-terminal real run, offline in-process run | `main.py` |
