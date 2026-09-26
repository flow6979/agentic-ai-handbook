**Language:** [Hinglish](TESTING.md) · English

# 02 · Web Search: how to test and tinker

## 1. Offline demo
```bash
python 03-web-agents/02-web-search/main.py --offline
```
This uses fake DuckDuckGo HTML and a scripted LLM. At the end of the output you will see:
```
[queries=['python 3.13 new features']]
[citations verified=2 unverified=[]]
```

## 2. Real run
```bash
# DuckDuckGo (no key)
python 03-web-agents/02-web-search/main.py "What changed in Python 3.13?"
python 03-web-agents/02-web-search/main.py "Who won the most recent Cricket World Cup?"

# Tavily (more reliable): put TAVILY_API_KEY=tvly-... in .env, then run the same command
```
To test only the search provider (no LLM):
```bash
cd 03-web-agents/02-web-search
../../.venv/bin/python -c "from websearch_providers import get_search_provider as g; [print(r) for r in g().search('rust async book', 3)]"
```
**What to look for:**
- `[search:duckduckgo:tool] web_search(...)`: is the model making short keyword queries?
- Did the model do a 2nd search when the first results were weak?
- `citations unverified=[...]` should be empty. If anything shows up, the model invented a URL.
- If you get `SearchError: DuckDuckGo blocked`, wait a bit, or use a Tavily key.

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/02-web-search -v
```
| Test | What it proves |
|---|---|
| `test_ddg_parser_extracts_real_urls_and_skips_ads` | Extracts the real URL from the redirect wrapper, and skips ads |
| `test_ddg_block_page_raises_clear_error` | A clear error on the bot-check page |
| `test_tavily_normalizes_to_same_shape` | Both providers return the same `SearchResult` shape, and Bearer auth is sent |
| `test_dedupe_ignores_fragment_www_and_trailing_slash` | Duplicate URLs are merged |
| `test_verify_citations_flags_made_up_urls` | A fake URL gets caught |

## 4. Tinker 🔧
1. **New provider:** write a `BraveProvider` (`https://api.search.brave.com/res/v1/web/search`, header `X-Subscription-Token`). Map the response's `web.results[]` to `SearchResult`. Write a fixture and a test too.
2. **Fallback provider:** build `FallbackSearch([Tavily, DuckDuckGo])`. If the first provider raises `SearchError`, try the next (the same pattern as `agentkit.FallbackLLM`).
3. **Citation enforcement:** in `main.py`, if `unverified` is non-empty, send the agent a follow-up message: "Remove or replace these unverified URLs: ...". Use `history=result.messages`.
4. **Domain filter:** add `site:` support to the tool, or block some domains from the results (such as content farms).
5. **Search cache:** plug in the `TTLCache` from 01-api-tools so the same query is hit only once.
6. **Date check:** remove the date from `SYSTEM` and ask "what is the latest Python version?". Compare the answers.
