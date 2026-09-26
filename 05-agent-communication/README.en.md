**Language:** [Hinglish](README.md) · English

# 05 · Agent Communication: how agents talk to each other (and to tools)

A single agent on its own is limited. As soon as you have 2+ agents (or an agent plus external tools), the questions
start: **how does a message travel, who waits, where does state live, and how is trust established?**
This section has one small project for each style.

## Folders (recommended order)

| # | Folder | Style | In one line |
|---|---|---|---|
| 01 | [01-direct-message-passing](01-direct-message-passing/) | In-process, direct | Typed envelopes (`from/to/type/payload/correlation_id`). Sync request/response vs fire-and-forget |
| 02 | [02-agent-as-tool](02-agent-as-tool/) | In-process, hierarchical | One agent calls another agent like a **tool**; control comes back to the caller |
| 03 | [03-handoffs](03-handoffs/) | In-process, transfer | The agent **transfers control** of the conversation itself ("handing you over to the billing agent") |
| 04 | [04-shared-blackboard](04-shared-blackboard/) | Shared state | Agents write to and read from a common board; they never talk to each other directly |
| 05 | [05-event-bus-pubsub](05-event-bus-pubsub/) | Async, mediated | Publish/subscribe on topics. The producer does not even know the consumer exists (like Kafka/Redis/NATS) |
| 06 | [06-http-agent-services](06-http-agent-services/) | Networked, custom | Every agent is a REST microservice. Registry, async jobs, retries |
| 07 | [07-mcp](07-mcp/) | Networked/stdio, **standard** | **Agent ↔ tools/data** protocol (MCP): server, host, HTTP, auth, security |
| 08 | [08-a2a](08-a2a/) | Networked, **standard** | **Agent ↔ agent** protocol (A2A): Agent Card, Tasks, streaming, multi-vendor |

The logic behind the order: first **inside a single process** (01→04), then **async/decoupled** (05), then
your own custom protocol over the **network** (06), and finally the **industry standards** (07 MCP, 08 A2A)
that standardize the problems you hit in 06.

## Taxonomy: a map of communication styles

```
                              AGENT COMMUNICATION
                                      │
          ┌───────────────────────────┼───────────────────────────────┐
          │                           │                               │
     WHERE do they run?        WHEN does the reply come?       HOW are they connected?
          │                           │                               │
   ┌──────┴───────┐            ┌──────┴────────┐          ┌───────────┼──────────────┐
 In-process    Networked     Sync           Async       Direct     Mediated      Shared state
 (01-05)       (06-08)     (request/     (fire-and-    (A→B       (A→broker→B   (A→board←B
 fast, simple  scale, sep.  response,     forget, pub/   directly)  / orchestr.)  blackboard,
 1 deploy      teams/langs  you wait)     sub, polling,  01,02,03   05, 02/08     DB, files)
                                          streaming)                orchestrator  04
                             01,02,06     01,05,06,08
                             07,08
          │
          └──► Within networked: talking to WHOM?
                   ┌──────────────────────┴───────────────────────┐
             Agent ↔ Tool/Data                              Agent ↔ Agent
             (the other side is a "dumb" function)          (the other side is an agent that thinks)
                   │                                              │
            MCP (07)  · plain function calling            A2A (08) · custom REST (06)
                                                          · ACP / ANP / AGNTCY (below)
```

### The 3 shapes of control flow (the most important difference in-process)
```
 AGENT-AS-TOOL (02)            HANDOFF (03)                  BLACKBOARD (04)
   Manager                      Triage ──► Billing             ┌──────────────┐
   │  ask(researcher)            (triage is out of the loop,   │  BOARD       │
   │ ◄── result                   billing now talks to the     │ facts, tasks │
   │  ask(writer)                  user directly)              └──▲───▲───▲───┘
   │ ◄── result                                                   A   B   C  (nobody calls
   ▼ final answer (the manager's)                                 anybody)
```

## Comparison table

| Style | Coupling | Latency | Scale | Failure handling | Debugging | Best for |
|---|---|---|---|---|---|---|
| 01 Direct messages | High (A knows B) | Lowest | 1 process | Simple (exceptions) | Easy | Small fixed pipelines |
| 02 Agent-as-tool | Medium | Low | 1 process | The caller handles it | Easy (one call tree) | Manager + specialists |
| 03 Handoffs | Medium | Low | 1 process | Risk of loops/ping-pong | Medium | Customer support triage |
| 04 Blackboard | Low | Medium | 1 process / shared DB | Stale/conflicting writes | Medium (inspect the board) | Open-ended problem solving |
| 05 Pub/Sub | **Lowest** | Async | High (broker) | Retries, DLQ, ordering | Hard (distributed) | Event-driven pipelines, many consumers |
| 06 Custom HTTP | Medium | Network | High | Timeouts, retries, idempotency | Hard | Internal microservice agents |
| 07 MCP | Low (standard) | Network/IPC | High | `isError`, protocol errors | Inspector | Reusable tools across apps |
| 08 A2A | Low (standard) | Network | High | Task states, cancel, polling | Medium | Cross-team/vendor agents, long tasks |

## Decision flow: which one should I use?

```
                       Start: two things need to talk
                                    │
                 Is the other side a "tool/data source" (does not think for itself)?
                     ┌──────── yes ─────────┴──────── no (it is an agent too) ─────┐
                     ▼                                                              ▼
       Will many apps/agents reuse it,                          Everything in one process/codebase?
       or is it third-party?                                  ┌───── yes ──────┴───── no ───────┐
        ┌─ yes ──┴─ no ───┐                                   ▼                                 ▼
        ▼                 ▼                         Does the caller need the result back?  Another team/vendor,
   MCP (07)        plain @tool                      ┌─ yes ───┴─── no ───┐              need a standard?
                   (function calling)               ▼                    ▼             ┌─ yes ──┴─ no ───┐
                                              Agent-as-tool (02)   Transfer control?   ▼                 ▼
                                                                   ┌─yes──┴──no──┐   A2A (08)    Custom HTTP (06)
                                                                   ▼             ▼                 (or events: 05)
                                                              Handoff (03)   Collaborate on
                                                                             common state? ──► Blackboard (04)
                                                                             Events/many consumers? ──► Pub/Sub (05)
                                                                             Simple fixed flow ──► Direct msgs (01)
```

## Protocols: MCP vs A2A vs the rest

| | MCP | A2A | ACP | ANP | AGNTCY |
|---|---|---|---|---|---|
| What it connects | Agent ↔ tools/data | Agent ↔ agent | Agent ↔ agent | Agent ↔ agent (open internet) | Infra for agent networks |
| Origin | Anthropic (open) | Google → Linux Foundation | IBM / BeeAI (LF) | Community | Cisco-led collective |
| Transport | stdio, Streamable HTTP | HTTP JSON-RPC (+ SSE; gRPC in v0.3) | REST | HTTP + DIDs | directory/identity/observability specs |
| Unit of work | tool call | **Task** (stateful, multi-turn) | run/message | message | n/a |
| Discovery | host config / registries | Agent Card (`/.well-known/...`) | manifests | DID documents | agent directory |

- **ACP** was REST-first. The community has moved toward converging it with A2A.
- **ANP** focuses on decentralized identity (DIDs), so agents can recognize each other on the open internet.
- **AGNTCY** is building plumbing such as directory, identity and observability for an "Internet of Agents".

This landscape is changing fast. The practical combo today: **MCP (tools) + A2A (agents)**, with
in-process patterns (01-04) on the inside.

## Common production concerns for every pattern
- **Correlation IDs / trace IDs**: put an id on every message so a multi-agent flow can be traced (agentkit `Tracer` + ids).
- **Timeouts + retries + idempotency**: messages can be duplicated on the network. Make handlers idempotent.
- **Schemas**: use typed envelopes / DataPart / JSON Schema instead of free text.
- **Loop guards**: handoff ping-pong, agents calling each other forever. Keep a max on hops/steps.
- **Trust boundaries**: the output of another agent/tool = **untrusted input** (prompt injection). Put human approval on destructive actions.
- **Cost**: every hop burns LLM tokens. Where the flow is fixed, use code instead of an LLM.

Every folder has a `CONCEPTS.en.md` (theory + diagrams + "how this project uses it") and a `TESTING.en.md` (run it, test it, tinker with it).
