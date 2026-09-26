**Language:** [Hinglish](CONCEPTS.md) · English

# A2A Server: concepts (Agent2Agent protocol)

## What is A2A?
**A2A = an open standard for agents talking to each other.** Google started it, and it is now under the Linux
Foundation. MCP connects an agent to **tools**, A2A connects an agent to **other agents**.

```
                 MCP                                  A2A
  Agent ───────────────► Tool/Data         Agent ◄──────────────► Agent
  (the tool is "dumb":                      (there is a brain on both sides: the remote agent
   input -> output, no thinking)             thinks for itself, can ask questions, can run
                                             for hours, uses its own tools/LLM)
```

In a real system **both run together**:
```
 Orchestrator ──A2A──► Travel Agent ──MCP──► currency-rates server
             └─A2A──► Packing Agent ──MCP──► weather server
```

## Spec version (important)
This code follows the JSON-RPC shapes of **A2A v0.2.x**:
- methods: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`
- every object has a `kind` discriminator (`"task"`, `"message"`, `"text"`, `"status-update"`...)
- the Agent Card is served at `/.well-known/agent.json`

**v0.3.0** changed the card path to `/.well-known/agent-card.json`, and added things like a gRPC transport and signed cards.
That is why this server serves **both paths**.
The spec is in active development. Check the latest version at https://a2a-protocol.org before going to production.

## Core building blocks

### 1. Agent Card: the agent's "business card"
`GET /.well-known/agent.json` → JSON that says:
```json
{
  "name": "Travel & Currency Expert",
  "description": "Converts currencies and gives travel tips...",
  "url": "http://127.0.0.1:9001/",              ← JSON-RPC endpoint
  "capabilities": {"streaming": true, "pushNotifications": false},
  "defaultInputModes": ["text/plain", "application/json"],
  "skills": [{"id": "currency-conversion", "tags": ["currency","money"], "examples": ["Convert 100 USD to INR"]}],
  "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},   ← how to authenticate
  "security": [{"bearer": []}]
}
```
The client reads the card first, then decides: can this agent do my job (skills)? Does it support streaming? How do I authenticate?

### 2. Message and Parts
**Message** = one turn. `role` takes two values: `"user"` (the client) or `"agent"` (the remote agent). A message contains **Parts**:

| Part | When |
|---|---|
| `TextPart {kind:"text", text}` | normal conversation |
| `DataPart {kind:"data", data:{...}}` | structured JSON, such as forms, results, parameters |
| `FilePart {kind:"file", file:{name, mimeType, bytes\|uri}}` | files (base64 if small, a link if large) |

### 3. Task: the unit of work (stateful)
Every request creates a **Task** with its own `id`, `contextId`, `status`, `artifacts` and `history`.

**Task lifecycle (state machine):**
```
                    ┌──────────────┐
      message ────► │  submitted   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐  agent needs more info       ┌────────────────┐
                    │   working    │ ───────────────────────────► │ input-required │
                    └──┬───┬───┬───┘ ◄────────── client replies   └───────┬────────┘
                       │   │   │        on the same taskId                │ tasks/cancel
          ┌────────────┘   │   └───────────────┐                          ▼
          ▼                ▼                   ▼                   ┌────────────┐
   ┌────────────┐   ┌────────────┐      ┌────────────┐             │  canceled  │
   │ completed  │   │   failed   │      │  rejected  │             └────────────┘
   └────────────┘   └────────────┘      └────────────┘
   (terminal states: completed / failed / canceled / rejected -> no new messages on this task)
   (auth-required: like input-required, but credentials are needed)
```

### 4. Artifact vs Message
- **Message** = conversation: "working on it", "which currency?"
- **Artifact** = a deliverable, i.e. the task's output: a report, a file, a JSON result.

This agent's final answer is an artifact `travel-answer` that contains both a TextPart (for humans) and a
DataPart `{conversions:[...]}` (for machines).

### 5. contextId
Groups several tasks into one **conversation** (like a chat thread). For multi-turn the
client sends `taskId` (continue the same task) and `contextId` (the same conversation).

## Wire protocol: JSON-RPC 2.0 over HTTP

```
Client                                                   A2A Server
  │ GET /.well-known/agent.json ────────────────────────► │  discovery
  │ ◄──────────────────────────────── AgentCard ───────── │
  │                                                       │
  │ POST /  {"method":"message/send",                     │
  │          "params":{"message":{role:user, parts:[..]}}}│
  │                                            the executor runs (agent + tools)
  │ ◄── {"result": Task{status: input-required,           │
  │        status.message: "Which currency?"}}            │
  │                                                       │
  │ POST /  message/send {message:{taskId: T1, "INR"}} ──► │  continue the same task
  │ ◄── {"result": Task{status: completed, artifacts:[..]}}│
  │                                                       │
  │ POST /  tasks/get {id: T1} ─────────────────────────► │  check the status any time
  │ POST /  tasks/cancel {id: T1} ──────────────────────► │
```

### Streaming: `message/stream` (SSE)
For long tasks the client wants live updates. The response is `text/event-stream`, and every
event is a JSON-RPC response:
```
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"task","status":{"state":"submitted"},...}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"status-update","status":{"state":"working","message":..."calling convert_currency(...)"}}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"artifact-update","artifact":{...}}}
data: {"jsonrpc":"2.0","id":7,"result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```
In this project the agent's **tool calls are streamed live**: agentkit `Tracer` → asyncio queue → SSE.

### Three interaction styles
| Style | How | When |
|---|---|---|
| **Blocking** request/response | `message/send` (blocking=true), wait for the answer | short tasks (seconds) |
| **Streaming** | `message/stream` → SSE events | when the UI needs to show live progress |
| **Async + polling** | `message/send` (blocking=false) → a Task right away, then `tasks/get` | long tasks, the client may disconnect |
| **Push notifications** (not implemented) | the client gives a webhook URL, the server calls back | tasks that take hours/days |

### Error codes
| Code | Meaning |
|---|---|
| -32700 / -32600 / -32601 / -32602 / -32603 | Standard JSON-RPC: parse, invalid request, method not found, invalid params, internal |
| -32001 | TaskNotFound |
| -32002 | TaskNotCancelable (already terminal) |
| -32003 | PushNotificationNotSupported |
| -32004 | UnsupportedOperation (e.g. a new message on a completed task, or streaming unsupported) |

## Design principle: "Opaque agents"
The remote agent reveals nothing about its internals: which LLM, which tools, which
framework, what the prompts are. From the outside you only see the card and the protocol. The benefits:
- IP/prompts stay safe
- you can change the internal implementation (switch the LLM, change the framework) and the client will not even notice
- agents from different companies can talk to each other (project 03)

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
The official **a2a-sdk** (Python) has the same split: `AgentExecutor` (your code) + `EventQueue`
+ `DefaultRequestHandler` + `TaskStore`. The details are in 03's CONCEPTS.

## How do you get "input-required" out of an LLM?
An LLM has no concept of "state". So we create a **convention**: the system prompt
says that if information is missing, reply with `NEED_INPUT: <question>`. The executor sees this prefix and puts the task
into the `input-required` state. Another way: give it an `ask_user(question)` tool, and
pause the task when the LLM calls it.

## Security
- **AuthN**: declare `securitySchemes` in the card (bearer/OAuth2/apiKey/OpenID). The server must enforce it, here via `token=`.
- **AuthZ**: check on the server side who may use which skill.
- **Untrusted input**: a message from a remote agent = untrusted text. Prompt injection is possible, so add guardrails in the executor.
- **Resource limits**: `max_steps`, timeouts, task TTL. Otherwise someone will create infinite tasks and blow up your LLM bill.
- HTTPS is required in production. Signing the card (v0.3+) protects against spoofing.

## When A2A, when not
✅ When you need to use an agent from another team or company, when agents are deployed/scaled separately, when tasks are long or multi-turn.<br>
❌ When all agents live in one process/codebase. Then in-process calls (folders 01-04) are simpler and faster. And when the other side is a "dumb tool", use MCP.

## How this project uses it
| Concept | Where |
|---|---|
| Card, Message, Parts, Task, Artifact, events (pydantic, camelCase wire) | `a2a_protocol.py` |
| JSON-RPC + A2A error codes | `JSONRPCError`, `rpc_result`, `rpc_error` |
| Card discovery (both paths) | `a2a_server_lib.py` → `agent_card()` |
| Task state machine | `_apply()`, `_start_or_resume()`, `TERMINAL`, `INTERRUPTED` |
| Blocking / non-blocking / streaming | `rpc()` branches, `_sse()` |
| Cancel rules | `tasks/cancel` branch |
| Bearer auth + card security | `_check_auth`, `create_app(token=...)` |
| Agent inside (any LLM) | `a2a_travel_agent.py` → `make_executor()` (agentkit `Agent` in a thread) |
| Tool calls → live status updates | `QueueTracer` |
| input-required convention | `NEED_INPUT:` in `SYSTEM` + executor |
| TextPart + DataPart artifact | executor end (`conversions`) |
| Offline fake brain | `offline_llm()` |
