**Language:** [Hinglish](TESTING.md) · English

# 01 · API Tools: how to test and tinker

## Setup (once)
```bash
cd agentic-ai-handbook
python3 -m venv .venv && .venv/bin/pip install -e ".[all]"
cp .env.example .env      # fill in LLM_MODEL + one key (Groq/Gemini free tier, or local Ollama)
```
This project's APIs (Wikipedia, open-meteo, frankfurter) **need no key**. A key is needed only for the LLM.

## 1. Offline demo (no internet, no key)
```bash
python 03-web-agents/01-api-tools/main.py --offline
```
This uses fake APIs and a scripted LLM. You will see the trace on stderr:
```
[travel:tool] get_weather({'city': 'Paris'})
[travel:tool] convert_currency({...})       ← both in the same step (parallel tool calls)
[travel:tool] wikipedia_summary({...})
[travel:result] Paris right now: 18.2°C ...
[steps=3 ... http={'requests': 4, 'cache_hits': 0, 'retries': 0}]
```

## 2. Real LLM + real APIs
```bash
python 03-web-agents/01-api-tools/main.py
python 03-web-agents/01-api-tools/main.py "Tokyo ka 3 din ka weather aur 10000 INR kitne JPY hote hain?"
python 03-web-agents/01-api-tools/main.py "Who was Ada Lovelace? Keep it to 3 lines."
```
**What to look for:**
- Did the LLM choose the right tools? (look at the `[travel:tool]` lines in the trace)
- Did independent tools run in the same step? (good models do this)
- Do the numbers in the final answer match the tool output? If not, the model hallucinated.
- Requests and cache_hits in the `http={...}` stats.

You can also try the tools directly without an LLM:
```bash
cd 03-web-agents/01-api-tools
../../.venv/bin/python -c "from apitools_http import ApiClient; from apitools_tools import make_tools; \
t={x.name:x for x in make_tools(ApiClient())}; print(t['get_weather'].fn(city='Mumbai'))"
```

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/01-api-tools -v
```
| Test | What it proves |
|---|---|
| `test_weather_tool_combines_geocode_and_forecast` | 2 API calls, 1 clean output |
| `test_retry_on_503_then_success` | 2 retries on 503, then success |
| `test_timeout_exhausts_retries_and_raises` | a clear `ApiError` on network timeout |
| `test_404_is_not_retried` | permanent errors are not retried |
| `test_cache_avoids_second_request_and_expires` | the cache hits, and expires after the TTL (fake clock) |
| `test_tool_error_reaches_llm_as_text` | the agent does not crash when the API is down; the LLM sees the error |

## 4. Tinker 🔧
1. **New tool:** add `get_country_info(name)` using `https://restcountries.com/v3.1/name/<name>` (no key). Return only the capital, population and currency. Add a fixture and a test too.
2. **See the cache at work:** in `main.py`, run `agent.run()` twice (same question) and watch `cache_hits` grow in `api.stats`.
3. **Break the trimming:** change `trim(..., 1200)` in `wikipedia_summary` to `50` and see how the model's answer degrades. This shows the "context vs quality" trade-off.
4. **Simulate a failure:** in `apitools_fixtures.mock_handler`, return `httpx.Response(503)` for open-meteo and run `--offline`. The retries will show up in the trace.
5. **Bad docstring experiment:** change the `wikipedia_search` docstring to just `"search"` and run it with a real LLM. See whether the model uses the tool less, or wrongly.
6. **Persistent cache:** make `TTLCache` backed by SQLite or `shelve` so the cache survives a process restart.
