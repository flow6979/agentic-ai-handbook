# 05 · Agent Communication: agents aapas mein (aur tools se) baat kaise karte hain

Ek agent akela limited hota hai. Jaise hi 2+ agents (ya agent + external tools) aate hain, sawaal
uthta hai: **message kaise jayega, kaun wait karega, state kahan rahegi, aur trust kaise hoga?**
Is section mein har style ka ek chhota project hai.

## Folders (recommended order)

| # | Folder | Style | Ek line mein |
|---|---|---|---|
| 01 | [01-direct-message-passing](01-direct-message-passing/) | In-process, direct | Typed envelopes (`from/to/type/payload/correlation_id`). Sync request/response vs fire-and-forget |
| 02 | [02-agent-as-tool](02-agent-as-tool/) | In-process, hierarchical | Ek agent doosre agent ko **tool** ki tarah call karta hai; control wapas caller ke paas aata hai |
| 03 | [03-handoffs](03-handoffs/) | In-process, transfer | Agent conversation ka **control hi transfer** kar deta hai ("billing agent ko de raha hoon") |
| 04 | [04-shared-blackboard](04-shared-blackboard/) | Shared state | Agents ek common board pe likhte/padhte hain, seedhe ek doosre se baat nahi karte |
| 05 | [05-event-bus-pubsub](05-event-bus-pubsub/) | Async, mediated | Topics pe publish/subscribe. Producer ko consumer ka pata bhi nahi (Kafka/Redis/NATS jaisa) |
| 06 | [06-http-agent-services](06-http-agent-services/) | Networked, custom | Har agent ek REST microservice. Registry, async jobs, retries |
| 07 | [07-mcp](07-mcp/) | Networked/stdio, **standard** | **Agent ↔ tools/data** protocol (MCP): server, host, HTTP, auth, security |
| 08 | [08-a2a](08-a2a/) | Networked, **standard** | **Agent ↔ agent** protocol (A2A): Agent Card, Tasks, streaming, multi-vendor |

Order ka logic: pehle **ek process ke andar** (01→04), phir **async/decoupled** (05), phir
**network** pe apna custom protocol (06), aur aakhir mein **industry standards** (07 MCP, 08 A2A)
jo 06 ki problems ko standardize karte hain.

## Taxonomy: communication styles ka map

```
                              AGENT COMMUNICATION
                                      │
          ┌───────────────────────────┼───────────────────────────────┐
          │                           │                               │
     KAHAN chalte hain?        KAB jawab milta hai?            KAISE judte hain?
          │                           │                               │
   ┌──────┴───────┐            ┌──────┴────────┐          ┌───────────┼──────────────┐
 In-process    Networked     Sync           Async       Direct     Mediated      Shared state
 (01-05)       (06-08)     (request/     (fire-and-    (A→B       (A→broker→B   (A→board←B
 fast, simple  scale, alag  response,     forget, pub/   seedha)    / orchestr.)  blackboard,
 1 deploy      teams/langs  wait karo)    sub, polling,  01,02,03   05, 02/08     DB, files)
                                          streaming)                orchestrator  04
                             01,02,06     01,05,06,08                              
                             07,08                                             
          │
          └──► Networked ke andar: KISSE baat?
                   ┌──────────────────────┴───────────────────────┐
             Agent ↔ Tool/Data                              Agent ↔ Agent
             (doosri taraf "dumb" function)                 (doosri taraf khud sochne wala agent)
                   │                                              │
            MCP (07)  · plain function calling            A2A (08) · custom REST (06)
                                                          · ACP / ANP / AGNTCY (neeche)
```

### Control flow ke 3 shapes (in-process mein sabse important farak)
```
 AGENT-AS-TOOL (02)            HANDOFF (03)                  BLACKBOARD (04)
   Manager                      Triage ──► Billing             ┌──────────────┐
   │  ask(researcher)            (triage bahar ho gaya,        │  BOARD       │
   │ ◄── result                   billing ab user se           │ facts, tasks │
   │  ask(writer)                  seedha baat karta hai)      └──▲───▲───▲───┘
   │ ◄── result                                                   A   B   C  (koi kisi ko
   ▼ final answer (manager ka)                                    call nahi karta)
```

## Comparison table

| Style | Coupling | Latency | Scale | Failure handling | Debugging | Best for |
|---|---|---|---|---|---|---|
| 01 Direct messages | High (A ko B pata hai) | Lowest | 1 process | Simple (exceptions) | Easy | Chhote fixed pipelines |
| 02 Agent-as-tool | Medium | Low | 1 process | Caller handle karta hai | Easy (ek call tree) | Manager + specialists |
| 03 Handoffs | Medium | Low | 1 process | Loop/ping-pong ka risk | Medium | Customer support triage |
| 04 Blackboard | Low | Medium | 1 process / shared DB | Stale/conflicting writes | Medium (board dekho) | Open-ended problem solving |
| 05 Pub/Sub | **Lowest** | Async | High (broker) | Retries, DLQ, ordering | Hard (distributed) | Event-driven pipelines, many consumers |
| 06 Custom HTTP | Medium | Network | High | Timeouts, retries, idempotency | Hard | Internal microservice agents |
| 07 MCP | Low (standard) | Network/IPC | High | `isError`, protocol errors | Inspector | Reusable tools across apps |
| 08 A2A | Low (standard) | Network | High | Task states, cancel, polling | Medium | Cross-team/vendor agents, long tasks |

## Decision flow: kaunsa use karun?

```
                       Start: do cheezon ko baat karni hai
                                    │
                 Doosri taraf ek "tool/data source" hai (khud nahi sochta)?
                     ┌──────── haan ────────┴──────── nahi (woh bhi agent hai) ────┐
                     ▼                                                              ▼
       Kai apps/agents reuse karenge,                          Sab ek process/codebase mein?
       ya third-party hai?                                    ┌───── haan ─────┴───── nahi ─────┐
        ┌─ haan ─┴─ nahi ─┐                                   ▼                                 ▼
        ▼                 ▼                         Result wapas caller ko chahiye?     Doosri team/vendor,
   MCP (07)        plain @tool                      ┌─ haan ──┴── nahi ──┐              standard chahiye?
                   (function calling)               ▼                    ▼             ┌─ haan ─┴─ nahi ─┐
                                              Agent-as-tool (02)   Control transfer?   ▼                 ▼
                                                                   ┌─haan─┴─nahi─┐   A2A (08)    Custom HTTP (06)
                                                                   ▼             ▼                 (ya events: 05)
                                                              Handoff (03)   Common state pe
                                                                             collaborate? ──► Blackboard (04)
                                                                             Events/many consumers? ──► Pub/Sub (05)
                                                                             Simple fixed flow ──► Direct msgs (01)
```

## Protocols: MCP vs A2A vs baaki

| | MCP | A2A | ACP | ANP | AGNTCY |
|---|---|---|---|---|---|
| Kya jodta hai | Agent ↔ tools/data | Agent ↔ agent | Agent ↔ agent | Agent ↔ agent (open internet) | Infra for agent networks |
| Origin | Anthropic (open) | Google → Linux Foundation | IBM / BeeAI (LF) | Community | Cisco-led collective |
| Transport | stdio, Streamable HTTP | HTTP JSON-RPC (+ SSE; v0.3 mein gRPC) | REST | HTTP + DIDs | directory/identity/observability specs |
| Unit of work | tool call | **Task** (stateful, multi-turn) | run/message | message | n/a |
| Discovery | host config / registries | Agent Card (`/.well-known/...`) | manifests | DID documents | agent directory |

- **ACP** REST-first tha. Community ne isse A2A ke saath converge karne ki disha li.
- **ANP** decentralized identity (DID) pe focus karta hai, taaki open internet pe agents ek doosre ko pehchaan sakein.
- **AGNTCY** "Internet of Agents" ke liye directory, identity aur observability jaisa plumbing bana raha hai.

Yeh landscape tez badal raha hai. Aaj practical combo: **MCP (tools) + A2A (agents)**, aur andar
in-process patterns (01-04).

## Har pattern ke common production concerns
- **Correlation IDs / trace IDs**: har message mein ek id rakho taaki multi-agent flow trace ho sake (agentkit `Tracer` + ids).
- **Timeouts + retries + idempotency**: network pe message duplicate ho sakta hai. Handler ko idempotent banao.
- **Schemas**: free text ki jagah typed envelopes / DataPart / JSON Schema use karo.
- **Loop guards**: handoff ping-pong, agents ka ek doosre ko infinitely call karna. Max hops/steps rakho.
- **Trust boundaries**: doosre agent/tool ka output = **untrusted input** (prompt injection). Destructive actions pe human approval lagao.
- **Cost**: har hop pe LLM tokens lagte hain. Jahan flow fixed hai wahan LLM ki jagah code use karo.

Har folder mein `CONCEPTS.md` (Hinglish theory + diagrams + "is project mein kaise") aur `TESTING.md` (chalao, test karo, tinker karo) hain.
