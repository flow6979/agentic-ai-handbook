**Language:** [Hinglish](TESTING.md) · English

# 03 · Supervisor Team: Test & Tinker

## Run

```bash
python 06-multi-agent-systems/03-supervisor-team/main.py --offline
python 06-multi-agent-systems/03-supervisor-team/main.py "Is a heat pump worth it?"
# strong supervisor, cheap workers
LLM_MODEL_SUPERVISOR=anthropic:claude-sonnet-5 LLM_MODEL=groq:llama-3.1-8b-instant \
  python 06-multi-agent-systems/03-supervisor-team/main.py "Should I install solar panels?"
```

Expected (offline): 5 board entries (researcher, writer, critic, writer, critic) and `ANSWER (finish, 6 rounds)` containing "6-10 years".

Note: research notes exist only for `solar`, `wind` and `heat pump` (the `KNOWLEDGE` dict). For other topics the researcher will say "No notes found".

## Tests

```bash
pytest 06-multi-agent-systems/03-supervisor-team -v
```

| Test | What it proves |
|---|---|
| `test_full_flow_with_critic_rewrite` | After the critic's issues there is a rewrite, then FINISH |
| `test_worker_gets_only_relevant_context` | The critic gets draft + research, the researcher doesn't get the draft |
| `test_stuck_guard_forces_finish` | Same worker again and again → `stuck` |
| `test_max_rounds_guard` | It stops at the round limit |
| `test_search_tool` | Tool hit/miss |

## What to look for in traces

```
[supervisor:info] round 1: -> researcher (need facts)
[researcher:tool] search_notes({'query': 'solar'})
[supervisor:info] round 3: -> critic (review draft)
```
Read the routing `reason`: it tells you why the supervisor is calling whom. Real LLMs often skip the critic and say FINISH straight away. If that happens, tighten the supervisor prompt.

## Tinker 🔧

1. **A new worker**: add a `fact_checker` (`WORKERS`, `PROMPTS`, the `Route.next` Literal). Tell the supervisor prompt when to call it.
2. **Real search**: replace `search_notes` with the web search tool from section 03 (web agents).
3. **Board compression**: send only each worker's latest entry in `_board_text()`, and compare token usage.
4. **Run with `--max-rounds 3`**. You will see an incomplete answer and `stopped_reason=max_rounds`.
5. **Give the supervisor a weak model** (8B). How often do you get wrong routing or a premature FINISH?
6. **Parallel workers**: what if the supervisor could return a list, `"next": ["researcher","writer"]`? Change the schema and run them in parallel with `concurrent.futures`.
