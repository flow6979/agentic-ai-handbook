**Language:** [Hinglish](README.md) · English

# 01 · Production-ready, LLM-agnostic Agent

In this section we build an agent that runs on **any LLM** (OpenAI, Claude, Gemini, Groq, Ollama...)
and handles the real problems of **production**: security, cost, failures, memory, testing, deployment.
This is the **entry point** of the whole repo. `support-desk/CONCEPTS.en.md` also contains a walkthrough of the `common/agentkit` core
(agent loop, tool schemas, provider adapters, retry/fallback). Every other section uses that same core.

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

| Project | What you will learn |
|---|---|
| [`support-desk/`](support-desk/) | E-commerce support agent: SQLite-backed tools, refund approval policy, session memory with summarization, guardrails, rate limit, timeouts, graceful degradation, cost tracking, evals, CLI/REPL/HTTP/batch/SDK modes, Dockerfile |

## Recommended order

1. `support-desk/CONCEPTS.en.md` sections 1-3: what an agent is, the agent loop, the agentkit core (provider abstraction).
2. `support-desk/TESTING.en.md` step 1: run the `--offline` demo and read the trace.
3. CONCEPTS sections 4-5: the production architecture, one concept at a time. Keep the matching file open alongside (see the table in section 9).
4. Put a real LLM in `.env`, try refunds/approval in the REPL, then run `eval --live`.
5. The "Tinker" exercises.

After that, move on to `02-agentic-architectures/`: it covers the different "shapes" of the agent loop (ReAct, plan-execute, reflection...).
