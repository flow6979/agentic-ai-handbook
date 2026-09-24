# Multi-vendor A2A: interoperability ka asli matlab

## Scenario
Tum travel app bana rahe ho. Currency/tips ka agent tumhari team ne banaya hai (agentkit + Groq).
Packing ka agent **"Another Vendor Inc."** ka hai: unka code tumhare paas nahi hai, unhone koi
framework ya LLM use nahi kiya (rules hain), aur unki streaming bhi nahi hai.
Fir bhi tumhara orchestrator dono se baat karta hai. **Kyun? Kyunki wire contract same hai: A2A.**

```
                         ┌────────────────── Orchestrator (LLM provider B, e.g. Gemini) ──────────┐
                         │  AgentRegistry ─► cards padho ─► SkillRouter ─► ThreadPool fan-out      │
                         └────────┬──────────────────────────────┬──────────────────────────────┘
                                  │ A2A JSON-RPC                  │ A2A JSON-RPC
                                  ▼                               ▼
   ┌──────────── Vendor 1 (hum) ─────────────┐     ┌──────────── Vendor 2 (koi aur) ───────────┐
   │ Travel & Currency Expert                │     │ Packing Assistant                         │
   │ a2a_server_lib + agentkit Agent         │     │ raw FastAPI + dicts, NO shared code       │
   │ LLM provider A (e.g. Groq)              │     │ NO LLM (rule based)                       │
   │ streaming: true                         │     │ streaming: false                          │
   └─────────────────────────────────────────┘     └───────────────────────────────────────────┘
          andar kuch bhi ho ─── bahar same Agent Card + same JSON-RPC methods + same Task shape
```

## Interoperability ke 4 layers
| Layer | Kya same hona chahiye | Is demo mein |
|---|---|---|
| **Discovery** | Card ka format aur location | Dono `/.well-known/agent.json` serve karte hain |
| **Transport** | HTTP + JSON-RPC 2.0 | Dono `POST /` pe JSON-RPC lete hain |
| **Data model** | Message/Part/Task/Artifact shapes | Packing agent plain dicts se wahi shape banata hai, aur test pydantic models se validate karta hai |
| **Capabilities** | Kya support hai, yeh honestly batana | Packing: `streaming:false`, isliye client stream nahi karta (`test_client_respects_streaming_capability`) |

**Semantic interop** (sabse mushkil layer): dono ek hi "language" samjhein. Isiliye packing request mein
**DataPart** `{city, month, days}` bhejte hain, sirf text nahi. Structured data mein galat samajhne ki
gunjaish kam hoti hai. Text sirf fallback hai.

## Multi-LLM-provider design
```
LLM_MODEL_A = groq:llama-3.3-70b-versatile    -> Travel agent ke andar (tool calling)
LLM_MODEL_B = gemini:gemini-2.5-flash         -> Orchestrator (routing + final summary)
(Packing agent: koi LLM nahi)
```
Kyun alag providers?
- **Cost/latency**: routing ke liye sasta aur tez model, domain kaam ke liye strong model
- **Vendor independence**: ek provider down ho to baaki system chalta rahe
- **Reality**: alag teams/companies alag providers choose karti hain, aur A2A ko isse farak nahi padta

## Orchestration patterns jo yahan dikhte hain
1. **Deterministic fan-out (`plan_trip`)**: kaam pehle se pata hai (tips + budget + packing), isliye teeno requests **parallel** mein jaati hain, phir code results combine karta hai, aur optional LLM summary likhta hai.
   - ✅ fast (parallel), predictable, sasta
2. **LLM orchestrator (`--llm-orchestrator`)**: free-form sawaal aata hai, LLM khud decide karta hai kis agent ko bhejna hai (02 wala agent reuse).
   - ✅ flexible; ❌ slow, non-deterministic

Rule of thumb: **flow pata ho to code likho, na pata ho to LLM ko orchestrate karne do.**

## Official a2a-sdk se mapping
Yeh repo protocol ko **from scratch** implement karta hai, taaki concepts dikhein. Production mein
official SDK (`pip install a2a-sdk`) use karo. Rough mapping (a2a-sdk 0.2/0.3 ke naam, apne
installed version ke docs se confirm karna):

| Is repo mein | a2a-sdk mein |
|---|---|
| `a2a_protocol.py` pydantic models | `a2a.types` (`AgentCard`, `AgentSkill`, `Message`, `Task`, `TextPart`, `DataPart`...) |
| executor async generator | `AgentExecutor.execute(context, event_queue)` + `cancel()` |
| `RequestContext` | `RequestContext` |
| `yield ctx.status(...)` / `ctx.artifact(...)` | `TaskUpdater` / `event_queue.enqueue_event(...)` |
| `TaskStore` | `InMemoryTaskStore` (ya DB-backed) |
| `build_a2a_app` (FastAPI) | `DefaultRequestHandler` + `A2AStarletteApplication` / `A2AFastAPIApplication` |
| `A2AClient` (httpx) | `A2AClient` / `ClientFactory` + `A2ACardResolver` |

SDK tumhe spec updates, gRPC/REST transports, push notifications, aur edge cases free mein deta hai.
Is repo ka version seekhne ke liye hai.

## Other agent-to-agent protocols (awareness)
- **ACP** (Agent Communication Protocol, IBM/BeeAI): REST-first agent messaging. Community ne isse A2A ke saath merge karne ki disha li.
- **ANP** (Agent Network Protocol): decentralized identity (DIDs) aur open-internet agent discovery.
- **AGNTCY** (Cisco-led collective): agent directory, identity, observability ka infra ("Internet of Agents").

Yeh landscape tez badal raha hai. Aaj ke din A2A (agent↔agent) + MCP (agent↔tool) sabse zyada adopted combo hai.

## Kab multi-vendor A2A
✅ Partners ya doosri teams ke agents, marketplace of agents, alag deploy/scale cycles.<br>
❌ Ek hi team ka monolith. Wahan in-process multi-agent (06 section) simple hai, aur network ka overhead aur failures bekaar hain.

## Failure modes jinka dhyaan rakhna hai
- **Partial failure**: packing agent down hai, par travel agent chal raha hai. Plan phir bhi aana chahiye (graceful degradation). Yeh tinker exercise hai.
- **Latency stacking**: sequential calls ka latency jud jaata hai, isliye parallel fan-out karo.
- **Version skew**: vendor ne v0.3 path pe card shift kiya. Hamara client dono paths try karta hai.
- **Trust**: vendor ka output untrusted hai. Validate karo (schema), aur prompt-injection guard lagao.

## Is project mein kaise use ho raha hai
| Concept | Kahan |
|---|---|
| Hand-written A2A server (no shared lib, no LLM) | `a2a_packing_agent_raw.py` → `create_packing_app()` |
| Structured input via DataPart | `parse_request()` + `plan_trip()` ka `data=` |
| Honest capabilities (streaming false) | packing card + `A2AClient.stream()` check |
| Parallel fan-out orchestration | `a2a_trip_planner.py` → `plan_trip()` (ThreadPoolExecutor) |
| Optional LLM summary (provider B) | `plan_trip(summarizer=...)` |
| Different providers per agent | `main.py` → `LLM_MODEL_A`, `LLM_MODEL_B` |
| Real network, 2 servers | `main.py` default mode, `test_over_real_network` |
| LLM orchestrator reuse (02) | `main.py --llm-orchestrator` |
