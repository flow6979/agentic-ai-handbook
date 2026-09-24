# 08 · A2A (Agent2Agent protocol): agent ↔ agent ka standard

| Folder | Kya seekhoge |
|---|---|
| [01-a2a-server](01-a2a-server/) | From-scratch A2A server: Agent Card, JSON-RPC, Task lifecycle, Parts/Artifacts, SSE streaming, async polling, auth; andar agentkit agent |
| [02-a2a-client-orchestrator](02-a2a-client-orchestrator/) | Client: discovery, skill routing (rule + LLM), delegation, input-required multi-turn, stream/poll |
| [03-multi-vendor-demo](03-multi-vendor-demo/) | Interop: hand-written "other vendor" agent (no LLM) + hamara agent + orchestrator; alag LLM providers; official a2a-sdk mapping |

```
01 (server + protocol lib) ──► 02 (client + orchestrator) ──► 03 (2 vendors, parallel fan-out)
```
Spec: A2A **v0.2.x** JSON-RPC shapes (card dono paths pe: `/.well-known/agent.json` aur v0.3 ka `/.well-known/agent-card.json`).
