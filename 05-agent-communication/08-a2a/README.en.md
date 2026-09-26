**Language:** [Hinglish](README.md) · English

# 08 · A2A (Agent2Agent protocol): the standard for agent ↔ agent

| Folder | What you will learn |
|---|---|
| [01-a2a-server](01-a2a-server/) | A from-scratch A2A server: Agent Card, JSON-RPC, Task lifecycle, Parts/Artifacts, SSE streaming, async polling, auth; an agentkit agent inside |
| [02-a2a-client-orchestrator](02-a2a-client-orchestrator/) | Client: discovery, skill routing (rule + LLM), delegation, input-required multi-turn, stream/poll |
| [03-multi-vendor-demo](03-multi-vendor-demo/) | Interop: a hand-written "other vendor" agent (no LLM) + our agent + an orchestrator; different LLM providers; mapping to the official a2a-sdk |

```
01 (server + protocol lib) ──► 02 (client + orchestrator) ──► 03 (2 vendors, parallel fan-out)
```
Spec: A2A **v0.2.x** JSON-RPC shapes (the card is served on both paths: `/.well-known/agent.json` and v0.3's `/.well-known/agent-card.json`).
