**Language:** [Hinglish](TESTING.md) · English

# Testing: prompt chaining (blog writer)

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + key in `.env` (see the root `.env.example`).

## Run

```bash
# offline (fake LLM) - the first outline will fail the gate, and you will see the retry:
python 02-agentic-architectures/01-prompt-chaining/main.py --offline

# real LLM:
python 02-agentic-architectures/01-prompt-chaining/main.py "Kubernetes basics for backend devs" --tone witty
```

## What to look for

```
--- step log ---
  outline: gate failed (attempt 1): duplicate section headings   <- caught by the gate
  outline: ok (attempt 2)                                        <- retry with feedback
  draft: ok (attempt 1)
  polish: ok
```

- With a real LLM, everything will often pass on `attempt 1`. To see a gate failure, do Tinker #1.
- The final post must contain all the outline headings (the draft gate ensures this).

## Offline tests

```bash
pytest 02-agentic-architectures/01-prompt-chaining -v
```

| Test | What it proves |
|---|---|
| `test_outline_gate_rules` | count and duplicate rules |
| `test_draft_gate_catches_missing_section` | a heading missing in the draft -> fail |
| `test_full_chain_retries_failed_gate_with_feedback` | the gate's error went into the retry prompt, 4 LLM calls in total |
| `test_chain_stops_when_gate_keeps_failing` | the pipeline stops after N attempts |

## Tinker with it

1. **Strict gate**: add a rule to `check_outline`: "each heading max 5 words". Run with a real LLM and watch the retries.
2. **Map-reduce**: change `step_draft` so each section gets its own LLM call (you can even run them in parallel, see 03), then join them. Is the quality better? What about latency?
3. **LLM gate**: build a `check_on_topic(llm, topic, draft)` gate that gets `{on_topic: bool, reason}` via `llm_json`. Should it go before or after the deterministic gates? Why?
4. **Multi-model**: use `get_llm("groq:llama-3.1-8b-instant")` for the outline and a strong model for the draft. Pass two LLM params to `write_blog`.
5. **Remove a gate**: comment out `check_draft` and give a topic with `min_words=400`. Is the output acceptable without the gate?
