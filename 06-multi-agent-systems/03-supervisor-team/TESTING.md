# 03 · Supervisor Team — Test & Tinker

## Run

```bash
python 06-multi-agent-systems/03-supervisor-team/main.py --offline
python 06-multi-agent-systems/03-supervisor-team/main.py "Is a heat pump worth it?"
# strong supervisor, cheap workers
LLM_MODEL_SUPERVISOR=anthropic:claude-sonnet-5 LLM_MODEL=groq:llama-3.1-8b-instant \
  python 06-multi-agent-systems/03-supervisor-team/main.py "Should I install solar panels?"
```

Expected (offline): 5 board entries (researcher, writer, critic, writer, critic) aur `ANSWER (finish, 6 rounds)` jisme "6-10 years" hai.

Note: research notes sirf `solar`, `wind`, `heat pump` ke hain (`KNOWLEDGE` dict). Doosre topics pe researcher bolega "No notes found".

## Tests

```bash
pytest 06-multi-agent-systems/03-supervisor-team -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_full_flow_with_critic_rewrite` | Critic ke issues ke baad rewrite hota hai, phir FINISH |
| `test_worker_gets_only_relevant_context` | Critic ko draft+research milta hai, researcher ko draft nahi |
| `test_stuck_guard_forces_finish` | Same worker baar baar → `stuck` |
| `test_max_rounds_guard` | Round limit pe ruk jaata hai |
| `test_search_tool` | Tool hit/miss |

## Traces mein kya dekhna hai

```
[supervisor:info] round 1: -> researcher (need facts)
[researcher:tool] search_notes({'query': 'solar'})
[supervisor:info] round 3: -> critic (review draft)
```
Routing ke `reason` padho, isse pata chalta hai ki supervisor kyun kisko bula raha hai. Real LLMs aksar critic ko skip karke seedha FINISH bol dete hain. Aisa ho to supervisor prompt tight karo.

## Tinker karo 🔧

1. **Naya worker**: `fact_checker` add karo (`WORKERS`, `PROMPTS`, `Route.next` Literal). Supervisor prompt mein batao kab bulana hai.
2. **Real search**: `search_notes` ko section 03 (web agents) ke web search tool se replace karo.
3. **Board compression**: `_board_text()` mein sirf har worker ka latest entry bhejo, aur token usage compare karo.
4. **`--max-rounds 3`** pe chalao. Dekho answer adhoora aata hai aur `stopped_reason=max_rounds` hota hai.
5. **Supervisor ko weak model do** (8B). Kitni baar galat routing ya premature FINISH hota hai?
6. **Parallel workers**: agar supervisor `"next": ["researcher","writer"]` list de sake to? Schema badal ke `concurrent.futures` se parallel chalao.
