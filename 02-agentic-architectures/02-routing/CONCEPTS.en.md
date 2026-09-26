**Language:** [Hinglish](CONCEPTS.md) · English

# Routing

## 1. What is the concept?

First **classify** the input, then send it to the **specialised handler** built for that type.
Like a hospital reception: they look at the patient and decide whether to send them to cardiology or orthopedics.

```
                           ┌───────────────┐
                    ┌─────►│ billing       │  (billing prompt, cheap model)
                    │      └───────────────┘
  ticket ──►[ROUTER]├─────►│ technical     │  (engineer prompt)
                    │      └───────────────┘
                    ├─────►│ refund        │  (refund policy prompt)
                    │      └───────────────┘
                    ├─────►│ general       │
                    │      └───────────────┘
                    └─────►  HUMAN (low confidence / router fail)
```

**Why?** If one prompt handles every case, it becomes big and confusing, and
optimising one case breaks another. Routing = **separation of concerns**.

## 2. Router subtypes

| Type | How | Pros | Cons |
|---|---|---|---|
| **Rule-based** | keywords / regex | free, 0 ms, predictable, testable | brittle: misses "paisa wapas chahiye" ("I want my money back") |
| **LLM classifier** | ask the LLM for `{route, confidence, reason}` JSON | understands natural language | cost + latency, sometimes wrong |
| **Embedding / semantic** | embed the input, pick the nearest route by its examples | cheap, fast, no generation | needs examples, threshold tuning |
| **Hybrid** | rules first, then LLM, low confidence -> human | best of both | a bit more complex |
| **Model routing** | look at query difficulty, pick a cheap vs strong model | big cost savings | wrong route = poor answer |

```
HYBRID ROUTER (this project's hybrid_route):

  text ──► rule_route() ──match──► route (method=rule, confidence=1.0)     ← free
              │
           no match
              ▼
          llm_route() ──JSON invalid──► general + needs_human (method=fallback)
              │
          confidence < 0.6 ? ──yes──► needs_human (escalate)
              │ no
              ▼
          route (method=llm)
```

### Model routing (cost optimisation)

```
 query ──► complexity_score() ──► score < 2 ──► CHEAP model  (8B, fast, ~10x cheaper)
                                  score >= 2 ──► STRONG model (70B / frontier)
```
In real systems 60-80% of queries are easy -> if a cheap model handles them, you save a lot.
The score can come from a heuristic, a small classifier, or even an LLM.

## 3. Confidence and escalation

Ask the LLM router for a **confidence** too. Low confidence = "I don't know" -> a human or a safe default.
Note: an LLM's self-reported confidence is not perfectly calibrated; in production, tune the threshold on an eval set.

## 4. When to use it / when not

Use it when:
- There are clearly distinct categories that need different handling.
- The categories can be classified accurately (by rules or an LLM).
- You want to save cost (easy -> cheap model).

Don't use it when:
- There are only 1-2 cases; one good prompt is enough.
- The categories overlap a lot (one ticket is both billing + technical) -> think multi-label / orchestrator.

## 5. Production pitfalls

- **Rule order**: "refund for double payment" is both billing and refund. The order of the rules = priority (the `RULES` list).
- **Crashing on router failure**: if the JSON comes back wrong, use a safe default + escalate (`method=fallback`).
- **Silent misroutes**: log every decision (route, method, confidence) and review a sample weekly.
- **A strong model for the router**: give the router a cheap/fast model; it only classifies.
- **Category drift**: new kinds of tickets start arriving -> "general" fills up. Watch the metrics.

## 6. How this project uses it

| Concept | File / function |
|---|---|
| Rule-based router + priority order | `routing_router.py` -> `RULES`, `rule_route()` |
| LLM classifier (structured) | `llm_route()` -> `llm_json(..., RouteDecision)` with `ROUTER_SYSTEM` |
| Hybrid + escalation + safe fallback | `hybrid_route()` -> `Routed(method, needs_human)` |
| Model routing | `complexity_score()`, `pick_model()` |
| Specialised handlers | `HANDLER_PROMPTS` dict, `handle_ticket()` |
| Different models per role | `main.py`: `ROUTER_MODEL`, `CHEAP_MODEL`, `STRONG_MODEL` env vars |
