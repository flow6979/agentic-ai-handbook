**Language:** [Hinglish](README.md) · English

# Agentic AI Handbook: from zero to production-ready agents

A repo for learning, with code, how to build agents that run on **any LLM** (OpenAI, Claude, Gemini, Groq, local Ollama...).

Every project has two docs:
- **`CONCEPTS.en.md`**: the concept, with flow diagrams, plus "how it is used in this project"
- **`TESTING.en.md`**: how to run it, how to verify it works correctly, and "Tinker" exercises

Every project also runs without an API key (`--offline` mode and offline tests), so you can understand the flow first.

Every doc in the repo comes in two languages (Hinglish and English). The language switcher is at the top of each file.

## Roadmap

```
                    ┌─────────────────────────────┐
                    │  common/  agentkit (engine) │  ◄── start here
                    │  LLM adapters, tools, loop  │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
 01-production-agent     02-agentic-architectures     03-web-agents
 (one agent, a full      (workflows + agent           (data from the internet:
  production setup)       patterns, 13 projects)       APIs, search, pages)
        │                          │                          │
        ▼                          ▼                          ▼
 04-rag                   05-agent-communication      06-multi-agent-systems
 (user data, PDFs:        (agent ↔ agent: messages,   (teams with roles:
  every type of RAG)       handoffs, pub/sub, HTTP,    crew, supervisor, swarm,
                           MCP, A2A)                   debate...)
```

## Repo map

| Folder | What you will learn |
|---|---|
| [`common/`](common/CONCEPTS.en.md) | `agentkit`: multi-provider LLM layer (adapter pattern), `@tool`, agent loop, retry/fallback, structured output, embeddings, tracing, ScriptedLLM |
| [`01-production-agent/`](01-production-agent/README.en.md) | **support-desk**: guardrails, memory, human approval, rate limit, cost tracking, evals, CLI/API/batch invocation, Docker |
| [`02-agentic-architectures/`](02-agentic-architectures/README.en.md) | workflows vs agents, prompt chaining, routing, parallelization, ReAct, plan-and-execute, reflection/Reflexion, evaluator-optimizer, orchestrator-workers, ReWOO, tree-of-thoughts, human-in-the-loop, memory |
| [`03-web-agents/`](03-web-agents/README.en.md) | API tools, web search (DuckDuckGo/Tavily), page reader (robots, SSRF guard, injection), deep research agent, browser automation concepts |
| [`04-rag/`](04-rag/README.en.md) | RAG basics (chunking, embeddings), PDF chat, hybrid BM25+vector+rerank, persistent vector store, agentic/corrective RAG, RAG evaluation |
| [`05-agent-communication/`](05-agent-communication/README.en.md) | direct messages, agent-as-tool, handoffs, blackboard, event bus pub/sub, HTTP microservices, **MCP**, **A2A** |
| [`06-multi-agent-systems/`](06-multi-agent-systems/README.en.md) | role design, sequential crew, supervisor, hierarchical teams, group chat, debate + judge, swarm handoffs |

## Setup

```bash
git clone git@github.com:flow6979/agentic-ai-handbook.git
cd agentic-ai-handbook
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

cp .env.example .env
# pick one provider in .env, e.g.
#   LLM_MODEL=groq:llama-3.3-70b-versatile   + GROQ_API_KEY   (free tier)
#   LLM_MODEL=gemini:gemini-2.5-flash        + GEMINI_API_KEY (free tier)
#   LLM_MODEL=ollama:llama3.1                (local, free, `ollama pull llama3.1`)
```

**All offline tests** (no key, no internet):

```bash
pytest
```

**Any project:**

```bash
python 02-agentic-architectures/04-react/main.py --offline   # see the flow without a key
python 02-agentic-architectures/04-react/main.py             # real LLM (from .env)
```

## Changing the LLM = a config change, not a code change

```
LLM_MODEL=openai:gpt-4o-mini
LLM_MODEL=anthropic:claude-sonnet-5
LLM_MODEL=gemini:gemini-2.5-flash
LLM_MODEL=groq:llama-3.3-70b-versatile,ollama:llama3.1    # comma = fallback chain
LLM_MODEL_WRITER=anthropic:claude-sonnet-5                # multi-agent: per-role model
```

## Philosophy

- **Framework-free:** what LangChain/CrewAI/LangGraph do is here in small, readable code. Once the concept clicks, you can learn any framework in a day. Every README says what the concept is called in which framework.
- **Offline tests:** every flow is tested deterministically with `ScriptedLLM` (a fake LLM). The LLM's quality is judged separately through evals.
- **Production mindset:** max-steps, timeouts, retries, sending errors back to the model, and handling untrusted input, everywhere.

## Honest note

All the offline tests and `--offline` demos have been verified. **No runs against real LLM providers happened while building this repo** (no keys were available), so prompts may need a little tuning with a real model. The adapters' wire formats are unit-tested.

## Concepts ahead (next round)

Each section's README has a "left for later" list. The big items:
- Streaming (SSE/WebSocket), async agent loop
- Observability export (OpenTelemetry, Langfuse), prompt versioning, semantic/prompt caching
- LLM guard models (Llama Guard), LLM-as-judge calibration
- GraphRAG, contextual retrieval, HyDE/multi-query, text-to-SQL, multimodal RAG
- LLMCompiler, LATS/MCTS, CRITIC, mem0-style memory reconcile
- Durable queues, circuit breakers, mTLS/OAuth between agents
- Dynamic agent spawning, parallel teams, multi-agent vs single-agent ablation evals
- Fine-tuning vs RAG vs prompting, agent frameworks hands-on (LangGraph, CrewAI, OpenAI Agents SDK, Claude Agent SDK)
