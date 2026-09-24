# 02 · Web Search: agent ko search engine dena

## Concept

API tab kaam aata hai jab tumhe pata ho ki data *kahan* hai. Jab pata hi na ho ("Python 3.13 mein kya naya hai?"), tab **search** chahiye. Search tool LLM ko links aur snippets deta hai. Us basis pe LLM jawab deta hai, ya pages padhne ke liye aage badhta hai (project 03).

```
 User question
      │
      ▼
 ┌─────────┐  web_search("python 3.13 new features")   ┌────────────────────┐
 │   LLM   │ ─────────────────────────────────────────► │  SearchProvider    │
 │         │                                            │ ┌────────────────┐ │
 │         │ ◄───────────────────────────────────────── │ │ DuckDuckGo HTML│ │ (no key)
 │         │  - title / url / snippet  (normalized)     │ │ Tavily API     │ │ (key)
 └────┬────┘                                            │ │ Brave/SerpAPI..│ │
      │ answer + [1] citations                          │ └────────────────┘ │
      ▼                                                 └────────────────────┘
 verify_citations(): kya har URL sach mein results mein tha?
```

## Adapter pattern: providers badlo, agent ko pata na chale

Har provider ka format alag hota hai (HTML ya JSON, alag field names). Hum sabko ek hi shape mein normalize karte hain:

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
```

```
DuckDuckGo HTML ──parse──┐
Tavily JSON ─────map─────┼──► list[SearchResult] ──► web_search tool ──► LLM
Brave JSON ──────map─────┘       (ek hi shape)
```
Yeh wahi idea hai jo agentkit mein LLM providers ke liye use hua tha (OpenAI/Anthropic → neutral `Message`).

## Search providers ke subtypes

| Type | Example | Key? | Pros | Cons |
|---|---|---|---|---|
| **HTML scraping** | DuckDuckGo html endpoint | ❌ | Free, bina signup | Fragile (HTML badla to parser toota), bot-block, ToS grey area |
| **LLM-oriented search API** | Tavily, Exa, Perplexity API | ✅ | Clean content snippets, agents ke liye bana | Paid (free tier hota hai) |
| **Classic SERP API** | Brave Search API, SerpAPI, Bing (retired), Google Custom Search | ✅ | Real search engine quality | Paid, sirf snippets milte hain (pages khud padhne padte hain) |
| **Built-in / native** | OpenAI/Anthropic/Gemini ke server-side web search tools | provider key | Zero code | Vendor lock-in, control kam |
| **Private / site search** | Elasticsearch, Algolia, apna index | apna | Internal docs pe | Setup chahiye (04-rag dekho) |

Yahan hum DuckDuckGo (default, no key) aur Tavily (`TAVILY_API_KEY` set ho to) implement karte hain. `get_search_provider()` khud decide karta hai kaunsa use karna hai.

## Citations: "grounding" aur hallucination check

Search wala answer tabhi trustworthy hai jab usme **source ho aur woh source asli ho**. LLM kabhi kabhi bilkul real lagne wale fake URLs bana deta hai. Isliye:

```
  answer text ──extract URLs──► [u1, u2, u3]
                                     │
  SearchLog (agent ne jo results     │  normalize (www, /, #fragment hatao)
  sach mein dekhe) ──────────────────┤
                                     ▼
                 verified: [u1, u2]    unverified: [u3]  ← suspicious!
```
Production mein unverified URL milne pe answer ko flag karo, hata do, ya model se dobara likhwao.

## Pitfalls
- **Snippets ≠ poora sach.** Snippet chhota hota hai aur context ke bina misleading ho sakta hai. Important cheezon ke liye page padho (project 03).
- **Recency:** system prompt mein aaj ki date do (`main.py` mein `date.today()`), warna model ko nahi pata ki "latest" kya hai.
- **Query quality:** LLM kabhi pura sawaal hi search mein daal deta hai. Prompt mein bolo "short keyword queries".
- **Duplicate results:** same page `www` ke saath, bina `www` ke, ya `#fragment` ke saath aa sakta hai. `dedupe()` in sabko ek maanta hai.
- **Bot blocks:** DuckDuckGo zyada requests pe "anomaly" page deta hai. Hum ise pakad ke clear error dete hain.
- **Search results mein bhi prompt injection ho sakta hai:** snippet ka text attacker likh sakta hai. Details project 03 mein hain.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Normalized result shape | `websearch_providers.py` → `SearchResult` |
| DuckDuckGo HTML parse (stdlib `HTMLParser`) | `_DDGParser`, `_clean_ddg_url()`, `DuckDuckGoProvider` |
| Bot-block detection | `DuckDuckGoProvider.search()` → `SearchError("...blocked...")` |
| Tavily adapter (Bearer auth) | `TavilyProvider` |
| Provider auto-selection | `get_search_provider()` |
| URL normalize + dedupe | `normalize_url()`, `dedupe()` |
| Provider → tool, results log | `websearch_tools.py` → `make_search_tool()`, `SearchLog` |
| Citation verification | `verify_citations()` |
| Date-aware system prompt + citation rules | `main.py` → `SYSTEM` |
