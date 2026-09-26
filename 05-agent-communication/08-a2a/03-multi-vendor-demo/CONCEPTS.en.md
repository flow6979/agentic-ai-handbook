**Language:** [Hinglish](CONCEPTS.md) · English

# Multi-vendor A2A: what interoperability really means

## Scenario
You are building a travel app. The currency/tips agent was built by your team (agentkit + Groq).
The packing agent belongs to **"Another Vendor Inc."**: you don't have their code, they used no
framework or LLM (it is rules), and they don't support streaming either.
Your orchestrator still talks to both. **Why? Because the wire contract is the same: A2A.**

```
                         ┌────────────────── Orchestrator (LLM provider B, e.g. Gemini) ──────────┐
                         │  AgentRegistry ─► read cards ─► SkillRouter ─► ThreadPool fan-out       │
                         └────────┬──────────────────────────────┬──────────────────────────────┘
                                  │ A2A JSON-RPC                  │ A2A JSON-RPC
                                  ▼                               ▼
   ┌──────────── Vendor 1 (us) ──────────────┐     ┌──────────── Vendor 2 (someone else) ──────┐
   │ Travel & Currency Expert                │     │ Packing Assistant                         │
   │ a2a_server_lib + agentkit Agent         │     │ raw FastAPI + dicts, NO shared code       │
   │ LLM provider A (e.g. Groq)              │     │ NO LLM (rule based)                       │
   │ streaming: true                         │     │ streaming: false                          │
   └─────────────────────────────────────────┘     └───────────────────────────────────────────┘
          anything inside ─── outside: same Agent Card + same JSON-RPC methods + same Task shape
```

## The 4 layers of interoperability
| Layer | What has to be the same | In this demo |
|---|---|---|
| **Discovery** | The card's format and location | Both serve `/.well-known/agent.json` |
| **Transport** | HTTP + JSON-RPC 2.0 | Both accept JSON-RPC on `POST /` |
| **Data model** | Message/Part/Task/Artifact shapes | The packing agent builds the same shape from plain dicts, and the test validates it with the pydantic models |
| **Capabilities** | Honestly stating what is supported | Packing: `streaming:false`, so the client does not stream (`test_client_respects_streaming_capability`) |

**Semantic interop** (the hardest layer): both sides must understand the same "language". That is why the packing request
sends a **DataPart** `{city, month, days}`, not just text. Structured data leaves less room for
misunderstanding. Text is only a fallback.

## Multi-LLM-provider design
```
LLM_MODEL_A = groq:llama-3.3-70b-versatile    -> inside the Travel agent (tool calling)
LLM_MODEL_B = gemini:gemini-2.5-flash         -> Orchestrator (routing + final summary)
(Packing agent: no LLM)
```
Why different providers?
- **Cost/latency**: a cheap, fast model for routing, a strong model for domain work
- **Vendor independence**: if one provider is down, the rest of the system keeps running
- **Reality**: different teams/companies choose different providers, and A2A does not care

## Orchestration patterns shown here
1. **Deterministic fan-out (`plan_trip`)**: the work is known up front (tips + budget + packing), so all three requests go out **in parallel**, then code combines the results, and an optional LLM writes a summary.
   - ✅ fast (parallel), predictable, cheap
2. **LLM orchestrator (`--llm-orchestrator`)**: a free-form question comes in, and the LLM decides which agent to send it to (reusing the agent from 02).
   - ✅ flexible; ❌ slow, non-deterministic

Rule of thumb: **if you know the flow, write code; if you don't, let the LLM orchestrate.**

## Mapping to the official a2a-sdk
This repo implements the protocol **from scratch** so the concepts are visible. In production use the
official SDK (`pip install a2a-sdk`). A rough mapping (names from a2a-sdk 0.2/0.3, confirm against the docs of
your installed version):

| In this repo | In a2a-sdk |
|---|---|
| `a2a_protocol.py` pydantic models | `a2a.types` (`AgentCard`, `AgentSkill`, `Message`, `Task`, `TextPart`, `DataPart`...) |
| executor async generator | `AgentExecutor.execute(context, event_queue)` + `cancel()` |
| `RequestContext` | `RequestContext` |
| `yield ctx.status(...)` / `ctx.artifact(...)` | `TaskUpdater` / `event_queue.enqueue_event(...)` |
| `TaskStore` | `InMemoryTaskStore` (or DB-backed) |
| `build_a2a_app` (FastAPI) | `DefaultRequestHandler` + `A2AStarletteApplication` / `A2AFastAPIApplication` |
| `A2AClient` (httpx) | `A2AClient` / `ClientFactory` + `A2ACardResolver` |

The SDK gives you spec updates, gRPC/REST transports, push notifications, and edge cases for free.
This repo's version is for learning.

## Other agent-to-agent protocols (awareness)
- **ACP** (Agent Communication Protocol, IBM/BeeAI): REST-first agent messaging. The community has moved toward merging it with A2A.
- **ANP** (Agent Network Protocol): decentralized identity (DIDs) and open-internet agent discovery.
- **AGNTCY** (Cisco-led collective): infrastructure for agent directory, identity, observability (the "Internet of Agents").

This landscape is changing fast. As of today, A2A (agent↔agent) + MCP (agent↔tool) is the most widely adopted combo.

## When multi-vendor A2A
✅ Agents from partners or other teams, a marketplace of agents, separate deploy/scale cycles.<br>
❌ A monolith owned by one team. There, in-process multi-agent (section 06) is simpler, and the network overhead and failures are wasted.

## Failure modes to watch out for
- **Partial failure**: the packing agent is down, but the travel agent is running. The plan should still arrive (graceful degradation). This is a tinker exercise.
- **Latency stacking**: the latency of sequential calls adds up, so fan out in parallel.
- **Version skew**: the vendor moved the card to the v0.3 path. Our client tries both paths.
- **Trust**: the vendor's output is untrusted. Validate it (schema), and add a prompt-injection guard.

## How this project uses it
| Concept | Where |
|---|---|
| Hand-written A2A server (no shared lib, no LLM) | `a2a_packing_agent_raw.py` → `create_packing_app()` |
| Structured input via DataPart | `parse_request()` + the `data=` of `plan_trip()` |
| Honest capabilities (streaming false) | packing card + the `A2AClient.stream()` check |
| Parallel fan-out orchestration | `a2a_trip_planner.py` → `plan_trip()` (ThreadPoolExecutor) |
| Optional LLM summary (provider B) | `plan_trip(summarizer=...)` |
| Different providers per agent | `main.py` → `LLM_MODEL_A`, `LLM_MODEL_B` |
| Real network, 2 servers | `main.py` default mode, `test_over_real_network` |
| LLM orchestrator reuse (02) | `main.py --llm-orchestrator` |
