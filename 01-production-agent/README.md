# 01 · Production-ready, LLM-agnostic Agent

Is section mein hum ek aisa agent banate hain jo **kisi bhi LLM** (OpenAI, Claude, Gemini, Groq, Ollama...) pe chale
aur **production** ki asli problems handle kare: security, cost, failures, memory, testing, deployment.
Poore repo ka **entry point** yahi hai. `support-desk/CONCEPTS.md` mein `common/agentkit` core ka walkthrough bhi hai
(agent loop, tool schemas, provider adapters, retry/fallback). Wahi core baaki saare sections use karte hain.

## Map

```
                         PRODUCTION AGENT
                               │
   ┌──────────────┬────────────┼──────────────┬────────────────┬──────────────┐
   ▼              ▼            ▼              ▼                ▼              ▼
 LLM layer      Tools &      Memory       Guardrails     Observability    Invocation
 ─────────      Safety       ──────       ──────────     ─────────────    ──────────
 adapters       authz        summary +    input/output   request ids      CLI / REPL
 get_llm()      data-min     window       injection      JSON logs        HTTP API
 retry          tiers        session      PII redact     traces, cost     SDK import
 fallback       HITL         ownership    canary         evals            batch, Docker
 structured
 output
```

## Projects

| Project | Kya seekhoge |
|---|---|
| [`support-desk/`](support-desk/) | E-commerce support agent: SQLite-backed tools, refund approval policy, session memory with summarization, guardrails, rate limit, timeouts, graceful degradation, cost tracking, evals, CLI/REPL/HTTP/batch/SDK modes, Dockerfile |

## Recommended order

1. `support-desk/CONCEPTS.md` sections 1-3: agent kya hai, agent loop, agentkit core (provider abstraction).
2. `support-desk/TESTING.md` step 1: `--offline` demo chalao, trace padho.
3. CONCEPTS sections 4-5: production architecture, ek ek concept. Saath mein file kholo (section 9 ki table).
4. `.env` mein real LLM daalo, REPL mein refund/approval try karo, phir `eval --live`.
5. "Tinker karo" exercises.

Uske baad `02-agentic-architectures/` pe jao: wahan agent loop ke alag-alag "shapes" (ReAct, plan-execute, reflection...) hain.
