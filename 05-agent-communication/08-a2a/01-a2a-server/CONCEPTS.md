**Language:** Hinglish · [English](CONCEPTS.en.md)

# A2A Server: concepts (Agent2Agent protocol)

## A2A kya hai?
**A2A = agents ke beech baat-cheet ka open standard.** Ise Google ne start kiya aur ab yeh Linux
Foundation ke under hai. MCP agent ko **tools** se jodta hai, A2A agent ko **doosre agents** se.

```
                 MCP                                  A2A
  Agent ───────────────► Tool/Data         Agent ◄──────────────► Agent
  (tool "dumb" hai:                         (dono taraf dimaag hai: remote agent khud
   input -> output, koi soch nahi)           sochta hai, sawaal poochh sakta hai, ghanton
                                             chal sakta hai, apne tools/LLM use karta hai)
```

Ek real system mein **dono saath chalte hain**:
```
 Orchestrator ──A2A──► Travel Agent ──MCP──► currency-rates server
             └─A2A──► Packing Agent ──MCP──► weather server
```

## Spec version (important)
Yeh code **A2A v0.2.x** ke JSON-RPC shapes follow karta hai:
- methods: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`
- har object mein `kind` discriminator hota hai (`"task"`, `"message"`, `"text"`, `"status-update"`...)
- Agent Card `/.well-known/agent.json` pe milta hai

**v0.3.0** ne card path `/.well-known/agent-card.json` kar diya, aur gRPC transport aur signed cards jaisi cheezein jodi.
Isliye yeh server **dono paths** serve karta hai.
Spec active development mein hai. Production se pehle https://a2a-protocol.org pe latest version check karo.

## Core building blocks

### 1. Agent Card: agent ka "visiting card"
`GET /.well-known/agent.json` → JSON jo batata hai:
```json
{
  "name": "Travel & Currency Expert",
  "description": "Converts currencies and gives travel tips...",
  "url": "http://127.0.0.1:9001/",              ← JSON-RPC endpoint
  "capabilities": {"streaming": true, "pushNotifications": false},
  "defaultInputModes": ["text/plain", "application/json"],
  "skills": [{"id": "currency-conversion", "tags": ["currency","money"], "examples": ["Convert 100 USD to INR"]}],
  "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},   ← kaise authenticate karein
  "security": [{"bearer": []}]
}
```
Client pehle card padhta hai, phir decide karta hai: kya yeh agent mera kaam kar sakta hai (skills)? Streaming support karta hai? Auth kaise karni hai?

### 2. Message aur Parts
**Message** = ek turn. `role` do values leta hai: `"user"` (client) ya `"agent"` (remote agent). Message ke andar **Parts** hote hain:

| Part | Kab |
|---|---|
| `TextPart {kind:"text", text}` | normal baat |
| `DataPart {kind:"data", data:{...}}` | structured JSON, jaise forms, results, parameters |
| `FilePart {kind:"file", file:{name, mimeType, bytes\|uri}}` | files (chhoti ho to base64, badi ho to link) |

### 3. Task: kaam ki unit (stateful)
Har request ek **Task** banata hai jiska apna `id`, `contextId`, `status`, `artifacts` aur `history` hota hai.

**Task lifecycle (state machine):**
```
                    ┌──────────────┐
      message ────► │  submitted   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐  agent ko aur info chahiye   ┌────────────────┐
                    │   working    │ ───────────────────────────► │ input-required │
                    └──┬───┬───┬───┘ ◄────────── client same      └───────┬────────┘
                       │   │   │        taskId pe jawab bhejta hai        │ tasks/cancel
          ┌────────────┘   │   └───────────────┐                          ▼
          ▼                ▼                   ▼                   ┌────────────┐
   ┌────────────┐   ┌────────────┐      ┌────────────┐             │  canceled  │
   │ completed  │   │   failed   │      │  rejected  │             └────────────┘
   └────────────┘   └────────────┘      └────────────┘
   (terminal states: completed / failed / canceled / rejected -> ab is task pe naya message nahi)
   (auth-required: input-required jaisa, lekin credentials chahiye)
```

### 4. Artifact vs Message
- **Message** = baat-cheet: "working on it", "which currency?"
- **Artifact** = deliverable, yaani task ka output: report, file, JSON result.

Is agent ka final jawab ek artifact `travel-answer` hai jisme TextPart (insaan ke liye) aur
DataPart `{conversions:[...]}` (machines ke liye) dono hain.

### 5. contextId
Kai tasks ko ek **conversation** mein group karta hai (jaise chat thread). Multi-turn ke liye
client `taskId` (usi task ko continue karna) aur `contextId` (same conversation) bhejta hai.

## Wire protocol: JSON-RPC 2.0 over HTTP

```
Client                                                   A2A Server
  │ GET /.well-known/agent.json ────────────────────────► │  discovery
  │ ◄──────────────────────────────── AgentCard ───────── │
  │                                                       │
  │ POST /  {"method":"message/send",                     │
  │          "params":{"message":{role:user, parts:[..]}}}│
  │                                            executor chalta hai (agent + tools)
  │ ◄── {"result": Task{status: input-required,           │
  │        status.message: "Which currency?"}}            │
  │                                                       │
  │ POST /  message/send {message:{taskId: T1, "INR"}} ──► │  same task continue
  │ ◄── {"result": Task{status: completed, artifacts:[..]}}│
  │                                                       │
  │ POST /  tasks/get {id: T1} ─────────────────────────► │  kabhi bhi status check
  │ POST /  tasks/cancel {id: T1} ──────────────────────► │
```

### Streaming: `message/stream` (SSE)
Lambe tasks mein client ko live updates chahiye. Response `text/event-stream` hota hai, aur har
event ek JSON-RPC response hota hai:
```
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"task","status":{"state":"submitted"},...}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"status-update","status":{"state":"working","message":..."calling convert_currency(...)"}}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"artifact-update","artifact":{...}}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```
Is project mein agent ke **tool calls live stream hote hain**: agentkit `Tracer` → asyncio queue → SSE.

### Teen interaction styles
| Style | Kaise | Kab |
|---|---|---|
| **Blocking** request/response | `message/send` (blocking=true), jawab tak ruko | chhote tasks (seconds) |
| **Streaming** | `message/stream` → SSE events | UI ko live progress dikhani ho |
| **Async + polling** | `message/send` (blocking=false) → turant Task, phir `tasks/get` | lambe tasks, client disconnect ho sakta hai |
| **Push notifications** (implement nahi kiya) | client webhook URL deta hai, server callback karta hai | ghanton/dinon wale tasks |

### Error codes
| Code | Matlab |
|---|---|
| -32700 / -32600 / -32601 / -32602 / -32603 | Standard JSON-RPC: parse, invalid request, method not found, invalid params, internal |
| -32001 | TaskNotFound |
| -32002 | TaskNotCancelable (already terminal) |
| -32003 | PushNotificationNotSupported |
| -32004 | UnsupportedOperation (e.g. completed task ko dobara message, ya streaming unsupported) |

## Design principle: "Opaque agents"
Remote agent apne andar ke baare mein kuch nahi batata: kaunsa LLM hai, kaunse tools, kaunsa
framework, prompts kya hain. Bahar sirf card aur protocol dikhta hai. Iske fayde:
- IP/prompts safe rehte hain
- andar ka implementation badal sakte ho (LLM switch karo, framework badlo) aur client ko pata bhi nahi chalega
- alag companies ke agents ek doosre se baat kar sakte hain (03 project)

## Server = plumbing, Executor = intelligence
```
┌────────────────── a2a_server_lib.build_a2a_app ───────────────────┐
│  card endpoints · JSON-RPC parse/validate · auth · TaskStore       │
│  state machine (_apply) · blocking/non-blocking · SSE · cancel     │
│                        │ RequestContext(task, message)              │
│                        ▼                                           │
│   ┌─────────── executor (a2a_travel_agent.make_executor) ────────┐ │
│   │ yield status(working) ... agentkit Agent (any LLM + tools)   │ │
│   │ yield status(input-required) | artifact(...) + completed     │ │
│   └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```
Official **a2a-sdk** (Python) mein bhi yahi split hai: `AgentExecutor` (tumhara code) + `EventQueue`
+ `DefaultRequestHandler` + `TaskStore`. Details 03 ke CONCEPTS mein hain.

## "input-required" ko LLM se kaise nikaalein?
LLM ke paas "state" ka concept nahi hota. Isliye hum ek **convention** banate hain: system prompt
kehta hai, info kam ho to reply karo `NEED_INPUT: <sawaal>`. Executor yeh prefix dekh ke task ko
`input-required` state mein daal deta hai. Dusra tareeka: ek `ask_user(question)` tool do, aur
jab LLM usse call kare to task pause kar do.

## Security
- **AuthN**: card mein `securitySchemes` declare karo (bearer/OAuth2/apiKey/OpenID). Server enforce kare, yahan `token=` se.
- **AuthZ**: kaun kaunsa skill use kar sakta hai, yeh server side check karo.
- **Untrusted input**: remote agent ka message = untrusted text. Prompt injection ho sakta hai, isliye executor mein guardrails lagao.
- **Resource limits**: `max_steps`, timeouts, task TTL. Nahi toh koi infinite tasks bana ke tumhara LLM bill uda dega.
- Production mein HTTPS zaroori hai. Card ko sign karna (v0.3+) spoofing se bachata hai.

## Kab A2A, kab nahi
✅ Jab doosri team ya company ka agent use karna ho, agents alag deploy/scale hote hon, tasks lambe ya multi-turn hon.<br>
❌ Jab sab agents ek hi process/codebase mein hain. Tab in-process calls (01-04 folders) simple aur tez hain. Aur jab doosri taraf "dumb tool" ho, tab MCP use karo.

## Is project mein kaise use ho raha hai
| Concept | Kahan |
|---|---|
| Card, Message, Parts, Task, Artifact, events (pydantic, camelCase wire) | `a2a_protocol.py` |
| JSON-RPC + A2A error codes | `JSONRPCError`, `rpc_result`, `rpc_error` |
| Card discovery (dono paths) | `a2a_server_lib.py` → `agent_card()` |
| Task state machine | `_apply()`, `_start_or_resume()`, `TERMINAL`, `INTERRUPTED` |
| Blocking / non-blocking / streaming | `rpc()` branches, `_sse()` |
| Cancel rules | `tasks/cancel` branch |
| Bearer auth + card security | `_check_auth`, `create_app(token=...)` |
| Agent inside (any LLM) | `a2a_travel_agent.py` → `make_executor()` (agentkit `Agent` in a thread) |
| Tool calls → live status updates | `QueueTracer` |
| input-required convention | `NEED_INPUT:` in `SYSTEM` + executor |
| TextPart + DataPart artifact | executor end (`conversions`) |
| Offline fake brain | `offline_llm()` |
