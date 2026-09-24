# 02 · Web Search: test aur tinker kaise karein

## 1. Offline demo
```bash
python 03-web-agents/02-web-search/main.py --offline
```
Isme fake DuckDuckGo HTML aur scripted LLM use hote hain. Output ke end mein dikhega:
```
[queries=['python 3.13 new features']]
[citations verified=2 unverified=[]]
```

## 2. Real run
```bash
# DuckDuckGo (no key)
python 03-web-agents/02-web-search/main.py "What changed in Python 3.13?"
python 03-web-agents/02-web-search/main.py "Who won the most recent Cricket World Cup?"

# Tavily (zyada reliable): .env mein TAVILY_API_KEY=tvly-... daalo, phir wahi command
```
Sirf search provider test karna ho (bina LLM ke):
```bash
cd 03-web-agents/02-web-search
../../.venv/bin/python -c "from websearch_providers import get_search_provider as g; [print(r) for r in g().search('rust async book', 3)]"
```
**Kya dekhna hai:**
- `[search:duckduckgo:tool] web_search(...)`: kya model short keyword queries bana raha hai?
- Kya model ne 2nd search kiya jab pehle results kamzor the?
- `citations unverified=[...]` khaali hona chahiye. Kuch aaye to model ne URL banaya hai.
- `SearchError: DuckDuckGo blocked` aaye to thoda ruko, ya Tavily key use karo.

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/02-web-search -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_ddg_parser_extracts_real_urls_and_skips_ads` | Redirect wrapper se real URL nikalta hai, aur ads skip hote hain |
| `test_ddg_block_page_raises_clear_error` | Bot-check page pe clear error aata hai |
| `test_tavily_normalizes_to_same_shape` | Dono providers same `SearchResult` shape dete hain, aur Bearer auth jaata hai |
| `test_dedupe_ignores_fragment_www_and_trailing_slash` | Duplicate URLs merge hote hain |
| `test_verify_citations_flags_made_up_urls` | Fake URL pakda jaata hai |

## 4. Tinker karo 🔧
1. **Naya provider:** `BraveProvider` likho (`https://api.search.brave.com/res/v1/web/search`, header `X-Subscription-Token`). Response ke `web.results[]` ko `SearchResult` mein map karo. Fixture aur test bhi likho.
2. **Fallback provider:** `FallbackSearch([Tavily, DuckDuckGo])` banao. Pehla provider `SearchError` de to agla try ho (yeh `agentkit.FallbackLLM` jaisa hi pattern hai).
3. **Citation enforcement:** `main.py` mein agar `unverified` non-empty ho, to agent ko ek follow-up message bhejo: "Remove or replace these unverified URLs: ...". `history=result.messages` use karo.
4. **Domain filter:** tool mein `site:` support add karo, ya results se kuch domains block karo (jaise content farms).
5. **Search cache:** 01-api-tools ka `TTLCache` yahan lagao, taaki same query ek hi baar hit ho.
6. **Date check:** `SYSTEM` se date hata do aur poochho "what is the latest Python version?". Answer mein farak dekho.
