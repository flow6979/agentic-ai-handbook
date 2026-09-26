**Language:** Hinglish · [English](README.en.md)

# Agentic AI Handbook: zero se production-ready agents tak

Hinglish mein, code ke saath, **kisi bhi LLM** (OpenAI, Claude, Gemini, Groq, Ollama local...) pe chalne wale agents seekhne ka repo.

Har project mein do docs hain:
- **`CONCEPTS.md`**: concept Hinglish mein, flow diagrams ke saath, aur "is project mein kaise use ho raha hai"
- **`TESTING.md`**: kaise chalayein, kaise verify karein ki sahi chal raha hai, aur "Tinker karo" exercises

Har project bina API key ke bhi chalta hai (`--offline` mode aur offline tests), taaki flow pehle samajh aa jaye.

Repo ka har doc do bhashaon mein hai (Hinglish aur English). Har file ke top pe language switcher hai.

## Roadmap

```
                    ┌─────────────────────────────┐
                    │  common/  agentkit (engine) │  ◄── yahan se shuru karo
                    │  LLM adapters, tools, loop  │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
 01-production-agent     02-agentic-architectures     03-web-agents
 (ek agent, poora        (workflows + agent           (internet se data:
  production setup)       patterns, 13 projects)       APIs, search, pages)
        │                          │                          │
        ▼                          ▼                          ▼
 04-rag                   05-agent-communication      06-multi-agent-systems
 (user data, PDFs:        (agent ↔ agent: messages,   (roles ke saath teams:
  RAG ke saare types)      handoffs, pub/sub, HTTP,    crew, supervisor, swarm,
                           MCP, A2A)                   debate...)
```

## Repo map

| Folder | Kya seekhoge |
|---|---|
| [`common/`](common/CONCEPTS.md) | `agentkit`: multi-provider LLM layer (adapter pattern), `@tool`, agent loop, retry/fallback, structured output, embeddings, tracing, ScriptedLLM |
| [`01-production-agent/`](01-production-agent/README.md) | **support-desk**: guardrails, memory, human approval, rate limit, cost tracking, evals, CLI/API/batch invocation, Docker |
| [`02-agentic-architectures/`](02-agentic-architectures/README.md) | workflows vs agents, prompt chaining, routing, parallelization, ReAct, plan-and-execute, reflection/Reflexion, evaluator-optimizer, orchestrator-workers, ReWOO, tree-of-thoughts, human-in-the-loop, memory |
| [`03-web-agents/`](03-web-agents/README.md) | API tools, web search (DuckDuckGo/Tavily), page reader (robots, SSRF guard, injection), deep research agent, browser automation concepts |
| [`04-rag/`](04-rag/README.md) | RAG basics (chunking, embeddings), PDF chat, hybrid BM25+vector+rerank, persistent vector store, agentic/corrective RAG, RAG evaluation |
| [`05-agent-communication/`](05-agent-communication/README.md) | direct messages, agent-as-tool, handoffs, blackboard, event bus pub/sub, HTTP microservices, **MCP**, **A2A** |
| [`06-multi-agent-systems/`](06-multi-agent-systems/README.md) | role design, sequential crew, supervisor, hierarchical teams, group chat, debate + judge, swarm handoffs |

## Setup

```bash
git clone git@github.com:flow6979/agentic-ai-handbook.git
cd agentic-ai-handbook
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

cp .env.example .env
# .env mein ek provider chuno, e.g.
#   LLM_MODEL=groq:llama-3.3-70b-versatile   + GROQ_API_KEY   (free tier)
#   LLM_MODEL=gemini:gemini-2.5-flash        + GEMINI_API_KEY (free tier)
#   LLM_MODEL=ollama:llama3.1                (local, free, `ollama pull llama3.1`)
```

**Sab offline tests** (no key, no internet):

```bash
pytest
```

**Koi bhi project:**

```bash
python 02-agentic-architectures/04-react/main.py --offline   # bina key ke flow dekho
python 02-agentic-architectures/04-react/main.py             # real LLM (.env se)
```

## LLM badalna = config change, code change nahi

```
LLM_MODEL=openai:gpt-4o-mini
LLM_MODEL=anthropic:claude-sonnet-5
LLM_MODEL=gemini:gemini-2.5-flash
LLM_MODEL=groq:llama-3.3-70b-versatile,ollama:llama3.1    # comma = fallback chain
LLM_MODEL_WRITER=anthropic:claude-sonnet-5                # multi-agent: per-role model
```

## Philosophy

- **Framework-free:** LangChain/CrewAI/LangGraph jo karte hain, woh yahan ~chhote, padhne layak code mein hai. Concept samajh aa gaya to koi bhi framework 1 din mein seekh loge. Har README batata hai ki concept kis framework mein kis naam se hai.
- **Tests offline:** `ScriptedLLM` (fake LLM) se har flow deterministic test hota hai. LLM ki quality alag se evals se judge hoti hai.
- **Production mindset:** har jagah max-steps, timeouts, retries, errors model ko wapas bhejna, untrusted input handling.

## Honest note

Saare offline tests aur `--offline` demos verify kiye gaye hain. **Real LLM providers ke saath runs is repo ko banate waqt nahi chale** (keys available nahi thi), isliye real model ke saath prompts ko thoda tune karna pad sakta hai. Adapters ke wire formats unit-tested hain.

## Aage ke concepts (next round)

Har section ke README mein "baaki reh gaye" list hai. Bade items:
- Streaming (SSE/WebSocket), async agent loop
- Observability export (OpenTelemetry, Langfuse), prompt versioning, semantic/prompt caching
- LLM guard models (Llama Guard), LLM-as-judge calibration
- GraphRAG, contextual retrieval, HyDE/multi-query, text-to-SQL, multimodal RAG
- LLMCompiler, LATS/MCTS, CRITIC, mem0-style memory reconcile
- Durable queues, circuit breakers, mTLS/OAuth between agents
- Dynamic agent spawning, parallel teams, multi-agent vs single-agent ablation evals
- Fine-tuning vs RAG vs prompting, agent frameworks hands-on (LangGraph, CrewAI, OpenAI Agents SDK, Claude Agent SDK)
