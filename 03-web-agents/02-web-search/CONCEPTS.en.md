**Language:** [Hinglish](CONCEPTS.md) · English

# 02 · Web Search: giving the agent a search engine

## Concept

An API helps when you know *where* the data is. When you do not ("What's new in Python 3.13?"), you need **search**. A search tool gives the LLM links and snippets. Based on those, the LLM answers, or moves on to read the pages (project 03).

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
 verify_citations(): was every URL really in the results?
```

## The adapter pattern: swap providers without the agent noticing

Every provider has a different format (HTML or JSON, different field names). We normalize them all into one shape:

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
Brave JSON ──────map─────┘       (one shape)
```
This is the same idea agentkit uses for LLM providers (OpenAI/Anthropic → neutral `Message`).

## Subtypes of search providers

| Type | Example | Key? | Pros | Cons |
|---|---|---|---|---|
| **HTML scraping** | DuckDuckGo html endpoint | ❌ | Free, no signup | Fragile (parser breaks when the HTML changes), bot blocks, ToS grey area |
| **LLM-oriented search API** | Tavily, Exa, Perplexity API | ✅ | Clean content snippets, built for agents | Paid (has a free tier) |
| **Classic SERP API** | Brave Search API, SerpAPI, Bing (retired), Google Custom Search | ✅ | Real search engine quality | Paid, you only get snippets (you read the pages yourself) |
| **Built-in / native** | Server-side web search tools from OpenAI/Anthropic/Gemini | provider key | Zero code | Vendor lock-in, less control |
| **Private / site search** | Elasticsearch, Algolia, your own index | your own | For internal docs | Needs setup (see 04-rag) |

Here we implement DuckDuckGo (default, no key) and Tavily (when `TAVILY_API_KEY` is set). `get_search_provider()` decides which one to use.

## Citations: "grounding" and hallucination checks

A search-based answer is trustworthy only if it **has a source and that source is real**. LLMs sometimes invent fake URLs that look completely real. So:

```
  answer text ──extract URLs──► [u1, u2, u3]
                                     │
  SearchLog (results the agent       │  normalize (strip www, /, #fragment)
  actually saw) ─────────────────────┤
                                     ▼
                 verified: [u1, u2]    unverified: [u3]  ← suspicious!
```
In production, when you find an unverified URL, flag the answer, remove it, or have the model rewrite it.

## Pitfalls
- **Snippets ≠ the whole truth.** A snippet is short and can mislead without context. For important things, read the page (project 03).
- **Recency:** give today's date in the system prompt (`date.today()` in `main.py`), otherwise the model does not know what "latest" means.
- **Query quality:** the LLM sometimes pastes the whole question into search. Tell it in the prompt to use "short keyword queries".
- **Duplicate results:** the same page can come back with `www`, without `www`, or with a `#fragment`. `dedupe()` treats them all as one.
- **Bot blocks:** DuckDuckGo returns an "anomaly" page after too many requests. We catch it and raise a clear error.
- **Search results can carry prompt injection too:** an attacker can write the snippet text. Details in project 03.

## How it is used in this project

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
