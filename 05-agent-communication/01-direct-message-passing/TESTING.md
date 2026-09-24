# 01 · Direct Message Passing: Test aur tinker kaise karein

## Setup (ek baar, repo root se)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env    # ek provider ki key bharo (ya ollama)
```

## 1. Offline chalao (bina key ke)

```bash
python 05-agent-communication/01-direct-message-passing/main.py --offline
```

Output mein teen section aayenge:
- **RESPONSE**: final summary (translated)
- **MESSAGE LOG**: saare 6 messages, ids aur `corr=` ke saath
- **AUDIT**: fire-and-forget events jo `drain()` pe deliver hue

**Kya dekhna hai:** `translator -> summarizer response corr=<X>` mein X ussi
`summarizer -> translator request` ka id hai. Yahi correlation hai.

## 2. Real LLM ke saath

```bash
python 05-agent-communication/01-direct-message-passing/main.py "Paste any long English paragraph here" --lang Hindi
python 05-agent-communication/01-direct-message-passing/main.py "..." --lang French
```

`.env` mein `LLM_MODEL` badal ke dekho: `groq:...`, `gemini:...`, `ollama:...`.
Code same rehta hai, sirf provider badalta hai.

## 3. Offline tests

```bash
pytest 05-agent-communication/01-direct-message-passing -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_request_response_with_correlation` | response ka `correlation_id` = request ka `id` |
| `test_agent_to_agent_chain_and_fire_and_forget` | summarizer→translator chain; events `drain()` tak queue mein |
| `test_unknown_recipient_and_crash_become_error_envelopes` | galat address / exception se bus nahi girta |
| `test_validation_error_from_agent` | payload validation error envelope return karta hai |
| `test_ping_pong_is_bounded` | infinite A→A loop `max_depth` pe ruk jata hai |

## Tinker karo

1. **Naya agent:** `SentimentAgent` banao jo `{"text"}` leke `{"sentiment": "positive|negative"}` de.
   Summarizer se usko bhi call karwao aur payload mein sentiment add karo.
2. **Timeout:** `MessageBus.request` mein `time.monotonic()` se har delivery ka time napo aur
   `>2s` pe warning log karo. Real systems mein yahi latency SLO hota hai.
3. **Broadcast:** `bus.broadcast(payload)` banao jo saare agents ko event bheje. Kaunse agents
   ko events ignore karne chahiye, socho.
4. **Loop todo:** `max_depth=1` karke main chalao. Translator call fail hogi. Dekho summarizer
   `warning` ke saath gracefully kaise jawab deta hai.
5. **Persistent log:** `bus.log` ko JSONL file mein dump karo aur `jq` se ek correlation thread nikaalo.
