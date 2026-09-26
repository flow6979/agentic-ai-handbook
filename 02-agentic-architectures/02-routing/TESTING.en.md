**Language:** [Hinglish](TESTING.md) · English

# Testing: routing (support ticket router)

## Setup
Repo root: `pip install -e ".[all]"`, put `LLM_MODEL` + key in `.env`.
Optional (to see model routing), in `.env`:
```
ROUTER_MODEL=groq:llama-3.1-8b-instant
CHEAP_MODEL=groq:llama-3.1-8b-instant
STRONG_MODEL=groq:llama-3.3-70b-versatile
```
(if not set, all three use `LLM_MODEL`.)

## Run

```bash
python 02-agentic-architectures/02-routing/main.py --offline          # 6 sample tickets, fake LLMs
python 02-agentic-architectures/02-routing/main.py                    # real LLM, same samples
python 02-agentic-architectures/02-routing/main.py "paisa wapas chahiye, product toot gaya"
```

## What to look for

```
TICKET : I was charged twice for my subscription this month
ROUTE  : billing (via rule) model=<...cheap...> human=False      <- caught by a rule, the LLM router was never called

TICKET : something weird is happening
ROUTE  : technical (via llm) model=- human=True                  <- low confidence -> human

TICKET : Explain why ... Compare ...? ```Traceback```
ROUTE  : general (via llm) model=<...strong...>                  <- complex -> strong model
```

- `via rule` vs `via llm`: rules are cheaper; see how many tickets the rules handled.
- The rules will miss the Hinglish ticket ("paisa wapas chahiye", i.e. "I want my money back") because they use English keywords; the LLM router will catch it. That is the benefit of hybrid.

## Offline tests

```bash
pytest 02-agentic-architectures/02-routing -v
```
- `test_hybrid_skips_llm_when_rule_matches`: **zero** LLM calls on a rule match (the ScriptedLLM is empty; a call would fail).
- `test_hybrid_low_confidence_escalates`, `test_hybrid_router_failure_is_safe`: escalation paths.
- `test_model_routing`: easy -> cheap, hard -> strong.
- `test_handler_uses_route_specific_prompt`: the right system prompt was sent.

## Tinker with it

1. **Hinglish rules**: add patterns like `paisa wapas|refund chahiye` to `RULES`. Compare the rule vs LLM hit rate.
2. **Build an embedding router**: take 3-4 example sentences per route, embed them with `agentkit.get_embedder("local")`, and send the ticket to the nearest route (`cosine`). Compare its accuracy with the rule and LLM routers.
3. **Mini eval set**: make a list of 20 tickets + expected routes and print the accuracy of all three routers. Raise `min_confidence` from 0.6 to 0.8: how many more human escalations?
4. **Multi-label**: change `RouteDecision` to `routes: list[RouteName]` so "double charge, give me a refund" goes to both handlers. How will you combine the replies?
5. **Cost tracking**: multiply each reply's `usage` by the per-token price of the cheap/strong model and print the total cost. How much did model routing save?
