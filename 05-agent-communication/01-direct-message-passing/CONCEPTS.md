# 01 · Direct Message Passing (Envelopes)

## Basic idea kya hai?

Jab do agents ek hi process mein hain, sabse seedha tareeka hai ki ek agent dusre ko
**message bheje**. Lekin "message" sirf string nahi hona chahiye. Hum usko ek
**envelope (lifafa)** mein daalte hain:

```
┌──────────────────────── Envelope ────────────────────────┐
│ id:             2bf2ba06        ← har message ka unique id │
│ sender:         summarizer      ← kisne bheja             │
│ recipient:      translator      ← kisko bhejna hai        │
│ type:           request         ← request/response/event  │
│ correlation_id: None            ← response kis request ka │
│ ts:             1727170000.12   ← kab bheja               │
├───────────────────────────────────────────────────────────┤
│ payload: {"text": "...", "target_lang": "Hindi"}          │
│          ↑ asli data (andar ki chitthi)                   │
└───────────────────────────────────────────────────────────┘
```

**Kyun?** Kyunki multi-agent system mein sabse badi problem debugging hoti hai: *"kisne
kisko kya bola, aur yeh jawab kis sawaal ka tha?"* Envelope ke metadata se yeh sab trace ho jata hai.

## Do communication styles

### 1) Request / Response (synchronous)

Function call jaisa: bhejo aur jawab aane tak ruko.

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

`correlation_id` = "yeh jawab request B ka hai". Isse bina confusion ke nested calls chal jaati hain.

### 2) Fire-and-Forget (events)

Bhejo aur bhool jao. Jawab ki umeed nahi. Notifications, logs, analytics ke liye.

```
 translator ──event──► [ inbox queue ] ──(baad mein drain)──► audit
                 ↑
          turant aage badh jata hai, wait nahi karta
```

| | Request/Response | Fire-and-Forget |
|---|---|---|
| Caller wait karta hai? | Haan | Nahi |
| Jawab milta hai? | Haan (correlation_id ke saath) | Nahi |
| Use case | "Mujhe translation chahiye" | "Maine translate kar diya" (audit) |
| Failure pata chalta hai? | Turant (error envelope) | Nahi (alag monitoring chahiye) |

## Message types (subtypes)

- **request**: kuch karwana hai
- **response**: request ka successful jawab
- **error**: request fail hui (agent crash, unknown recipient, validation)
- **event**: kuch ho gaya, bas batana hai

## MessageBus (post office) kya karta hai?

```
           ┌────────────── MessageBus ──────────────┐
 send() ──►│  1. log mein likho (tracing)            │
request()─►│  2. recipient dhoondo (registry)        │──► agent.handle()
           │  3. crash? → error envelope             │
           │  4. depth check (ping-pong se bachao)   │
           └─────────────────────────────────────────┘
```

Production guards jo yahan dikhaye hain:

1. **Unknown recipient** crash nahi, error envelope ban jata hai.
2. **Agent exception** bhi error envelope ban jata hai, bus nahi girta.
3. **max_depth**: A → B → A → B... infinite loop LLM agents mein asli khatra hai
   (dono ek dusre se "clarify" karte rehte hain). Depth limit lagao.
4. **Log**: har message record hota hai. `bus.conversation(id)` se ek pura thread nikal sakte ho.

## Kab use karein, kab nahi?

**Use karo jab:**
- saare agents ek hi process/service mein hain
- chhota system hai (2-5 agents), latency kam chahiye
- simple, debuggable setup chahiye

**Mat use karo jab:**
- agents alag machines/services pe hain → HTTP (project 06) ya A2A (08)
- bahut saare consumers ek event sunte hain → pub/sub (project 05)
- agents ko shared state pe collaborate karna hai → blackboard (project 04)

## Common pitfalls

- **Payload mein free text bhejna** → receiver parse nahi kar pata. Payload dict/schema rakho.
- **correlation_id bhool jaana** → async duniya mein response match nahi hota.
- **Fire-and-forget mein errors gayab** → dead-letter / monitoring chahiye (project 05 dekho).
- **Cycle detection nahi** → token bill aur infinite loop.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Envelope + `reply()` (correlation id set karta hai) | `dm_bus.py` → `Envelope` |
| Post office, registry, log, depth guard | `dm_bus.py` → `MessageBus.request / send / drain` |
| Agent → agent call | `dm_bus.py` → `BusAgent.ask()` (request), `BusAgent.tell()` (event) |
| LLM translator | `dm_agents.py` → `TranslatorAgent` |
| Summarizer jo translator ko khud call karta hai | `dm_agents.py` → `SummarizerAgent.handle` |
| Fire-and-forget consumer | `dm_agents.py` → `AuditLogAgent` |
| Demo + message log print | `main.py` |

Flow:

```
user ─request─► summarizer ──LLM──► summary
                    │
                    ├─request─► translator ──LLM──► translation
                    │               └─event─► audit (queued)
                    └─event─► audit (queued)
bus.drain() → audit ko dono events milte hain
```
