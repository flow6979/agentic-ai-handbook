**Language:** Hinglish · [English](TESTING.en.md)

# Testing: prompt chaining (blog writer)

## Setup
Repo root se: `pip install -e ".[all]"`, aur `.env` mein `LLM_MODEL` + key (dekho root `.env.example`).

## Run

```bash
# offline (fake LLM) - pehla outline gate fail karega, retry dikhega:
python 02-agentic-architectures/01-prompt-chaining/main.py --offline

# real LLM:
python 02-agentic-architectures/01-prompt-chaining/main.py "Kubernetes basics for backend devs" --tone witty
```

## Kya dekhna hai

```
--- step log ---
  outline: gate failed (attempt 1): duplicate section headings   <- gate ne pakda
  outline: ok (attempt 2)                                        <- feedback ke saath retry
  draft: ok (attempt 1)
  polish: ok
```

- Real LLM mein aksar sab `attempt 1` pe pass ho jaayega. Gate fail dekhne ke liye Tinker #1 karo.
- Final post mein outline ki saari headings honi chahiye (draft gate ensure karta hai).

## Offline tests

```bash
pytest 02-agentic-architectures/01-prompt-chaining -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_outline_gate_rules` | count aur duplicate rules |
| `test_draft_gate_catches_missing_section` | draft mein heading missing -> fail |
| `test_full_chain_retries_failed_gate_with_feedback` | retry prompt mein gate ka error gaya, total 4 LLM calls |
| `test_chain_stops_when_gate_keeps_failing` | N attempts ke baad pipeline ruk jaati hai |

## Tinker karo

1. **Strict gate**: `check_outline` mein rule add karo "har heading max 5 words". Real LLM pe chalao aur retries dekho.
2. **Map-reduce**: `step_draft` ko badlo taaki har section ke liye alag LLM call ho (parallel bhi kar sakte ho, 03 dekho), phir join karo. Kya quality better hai? Latency?
3. **LLM gate**: ek `check_on_topic(llm, topic, draft)` gate banao jo `llm_json` se `{on_topic: bool, reason}` le. Deterministic gates se pehle ya baad lagana chahiye? Kyun?
4. **Multi-model**: outline ke liye `get_llm("groq:llama-3.1-8b-instant")` aur draft ke liye strong model. `write_blog` mein do LLM params pass karo.
5. **Gate hatao**: `check_draft` comment out karo aur `min_words=400` wala topic do. Kya output bina gate ke acceptable hai?
