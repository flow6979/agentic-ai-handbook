**Language:** [Hinglish](TESTING.md) · English

# 01 · Direct Message Passing: how to test and tinker

## Setup (once, from the repo root)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env    # fill in one provider's key (or use ollama)
```

## 1. Run offline (no key needed)

```bash
python 05-agent-communication/01-direct-message-passing/main.py --offline
```

The output has three sections:
- **RESPONSE**: the final (translated) summary
- **MESSAGE LOG**: all 6 messages, with ids and `corr=`
- **AUDIT**: the fire-and-forget events delivered on `drain()`

**What to look for:** in `translator -> summarizer response corr=<X>`, X is the id of that same
`summarizer -> translator request`. That is correlation.

## 2. With a real LLM

```bash
python 05-agent-communication/01-direct-message-passing/main.py "Paste any long English paragraph here" --lang Hindi
python 05-agent-communication/01-direct-message-passing/main.py "..." --lang French
```

Try changing `LLM_MODEL` in `.env`: `groq:...`, `gemini:...`, `ollama:...`.
The code stays the same; only the provider changes.

## 3. Offline tests

```bash
pytest 05-agent-communication/01-direct-message-passing -v
```

| Test | What it proves |
|---|---|
| `test_request_response_with_correlation` | the response's `correlation_id` = the request's `id` |
| `test_agent_to_agent_chain_and_fire_and_forget` | summarizer→translator chain; events stay queued until `drain()` |
| `test_unknown_recipient_and_crash_become_error_envelopes` | a wrong address / exception does not bring the bus down |
| `test_validation_error_from_agent` | a payload validation error returns an error envelope |
| `test_ping_pong_is_bounded` | an infinite A→A loop stops at `max_depth` |

## Tinker with it

1. **New agent:** build a `SentimentAgent` that takes `{"text"}` and returns `{"sentiment": "positive|negative"}`.
   Have the summarizer call it too and add the sentiment to the payload.
2. **Timeout:** in `MessageBus.request`, time each delivery with `time.monotonic()` and
   log a warning above `>2s`. In real systems this is exactly your latency SLO.
3. **Broadcast:** build `bus.broadcast(payload)` that sends an event to every agent. Think about which agents
   should ignore events.
4. **Break the loop:** run main with `max_depth=1`. The translator call will fail. Watch how the summarizer
   replies gracefully with a `warning`.
5. **Persistent log:** dump `bus.log` to a JSONL file and use `jq` to pull out one correlation thread.
