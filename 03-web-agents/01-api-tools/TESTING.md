**Language:** Hinglish · [English](TESTING.en.md)

# 01 · API Tools: test aur tinker kaise karein

## Setup (ek baar)
```bash
cd agentic-ai-handbook
python3 -m venv .venv && .venv/bin/pip install -e ".[all]"
cp .env.example .env      # LLM_MODEL + ek key bharo (Groq/Gemini free tier, ya Ollama local)
```
Is project ke APIs (Wikipedia, open-meteo, frankfurter) ko **kisi key ki zaroorat nahi**. Key sirf LLM ke liye chahiye.

## 1. Offline demo (no internet, no key)
```bash
python 03-web-agents/01-api-tools/main.py --offline
```
Isme fake APIs aur ek scripted LLM use hote hain. Stderr pe trace dikhega:
```
[travel:tool] get_weather({'city': 'Paris'})
[travel:tool] convert_currency({...})       ← dono ek hi step mein (parallel tool calls)
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
**Kya dekhna hai:**
- Kya LLM ne sahi tools chune? (trace mein `[travel:tool]` lines dekho)
- Kya independent tools ek hi step mein chale? (achhe models aisa karte hain)
- Final answer ke numbers tool output se match karte hain ya nahi. Mismatch mile to model ne hallucinate kiya.
- `http={...}` stats mein requests aur cache_hits.

Tools ko bina LLM ke seedha bhi try kar sakte ho:
```bash
cd 03-web-agents/01-api-tools
../../.venv/bin/python -c "from apitools_http import ApiClient; from apitools_tools import make_tools; \
t={x.name:x for x in make_tools(ApiClient())}; print(t['get_weather'].fn(city='Mumbai'))"
```

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/01-api-tools -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_weather_tool_combines_geocode_and_forecast` | 2 API calls, 1 clean output |
| `test_retry_on_503_then_success` | 503 pe 2 retries, phir success |
| `test_timeout_exhausts_retries_and_raises` | network timeout pe clear `ApiError` |
| `test_404_is_not_retried` | permanent errors pe retry nahi hota |
| `test_cache_avoids_second_request_and_expires` | cache hit hota hai, aur TTL ke baad expire hota hai (fake clock) |
| `test_tool_error_reaches_llm_as_text` | API down hone pe agent crash nahi karta, LLM ko error dikhta hai |

## 4. Tinker karo 🔧
1. **Naya tool:** `get_country_info(name)` add karo, `https://restcountries.com/v3.1/name/<name>` (no key) use karke. Sirf capital, population aur currency return karo. Fixture aur test bhi add karo.
2. **Cache ka asar dekho:** `main.py` mein `agent.run()` do baar chalao (same question) aur `api.stats` mein `cache_hits` badhte dekho.
3. **Trimming todo:** `wikipedia_summary` mein `trim(..., 1200)` ko `50` kar do aur dekho model ka answer kaise kharab hota hai. Isse "context vs quality" ka trade-off samajh aayega.
4. **Failure simulate karo:** `apitools_fixtures.mock_handler` mein open-meteo ke liye `httpx.Response(503)` return karo aur `--offline` chalao. Retries trace mein dikhenge.
5. **Bad docstring experiment:** `wikipedia_search` ki docstring ko sirf `"search"` kar do aur real LLM se chalao. Dekho ki model tool kam ya galat use karta hai ya nahi.
6. **Persistent cache:** `TTLCache` ko SQLite ya `shelve` backed banao taaki cache process restart ke baad bhi bacha rahe.
