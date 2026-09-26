**Language:** Hinglish · [English](TESTING.en.md)

# Testing: routing (support ticket router)

## Setup
Repo root: `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.
Optional (model routing dekhne ke liye), `.env` mein:
```
ROUTER_MODEL=groq:llama-3.1-8b-instant
CHEAP_MODEL=groq:llama-3.1-8b-instant
STRONG_MODEL=groq:llama-3.3-70b-versatile
```
(set nahi kiye to teeno `LLM_MODEL` use karenge.)

## Run

```bash
python 02-agentic-architectures/02-routing/main.py --offline          # 6 sample tickets, fake LLMs
python 02-agentic-architectures/02-routing/main.py                    # real LLM, same samples
python 02-agentic-architectures/02-routing/main.py "paisa wapas chahiye, product toot gaya"
```

## Kya dekhna hai

```
TICKET : I was charged twice for my subscription this month
ROUTE  : billing (via rule) model=<...cheap...> human=False      <- rule ne pakda, LLM router call hi nahi hua

TICKET : something weird is happening
ROUTE  : technical (via llm) model=- human=True                  <- low confidence -> human

TICKET : Explain why ... Compare ...? ```Traceback```
ROUTE  : general (via llm) model=<...strong...>                  <- complex -> strong model
```

- `via rule` vs `via llm`: rules sasti hain; dekho kitne tickets rules se nikal gaye.
- Hinglish ticket ("paisa wapas chahiye") rules miss karenge (English keywords), LLM router pakdega. Yahi hybrid ka fayda hai.

## Offline tests

```bash
pytest 02-agentic-architectures/02-routing -v
```
- `test_hybrid_skips_llm_when_rule_matches`: rule match pe LLM call **zero** (ScriptedLLM empty hai; call hota to fail).
- `test_hybrid_low_confidence_escalates`, `test_hybrid_router_failure_is_safe`: escalation paths.
- `test_model_routing`: easy -> cheap, hard -> strong.
- `test_handler_uses_route_specific_prompt`: sahi system prompt gaya.

## Tinker karo

1. **Hinglish rules**: `RULES` mein `paisa wapas|refund chahiye` jaise patterns add karo. Rule vs LLM hit-rate compare karo.
2. **Embedding router banao**: har route ke 3-4 example sentences lo, `agentkit.get_embedder("local")` se embed karo, ticket ko nearest route pe bhejo (`cosine`). Rule aur LLM router se accuracy compare karo.
3. **Mini eval set**: 20 tickets + expected route ki list banao, teeno routers ki accuracy print karo. `min_confidence` 0.6 se 0.8 karo: kitne zyada human escalations?
4. **Multi-label**: `RouteDecision` ko `routes: list[RouteName]` banao taaki "double charge, refund do" dono handlers ko jaaye. Replies kaise combine karoge?
5. **Cost tracking**: har reply ke `usage` ko cheap/strong model ke per-token price se multiply karke total cost print karo. Model routing se kitna bacha?
