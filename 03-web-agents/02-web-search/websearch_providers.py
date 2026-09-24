"""Pluggable web search providers, sab ek hi `SearchResult` shape return karte hain.

    DuckDuckGoProvider  -> html.duckduckgo.com, no key, HTML parse (fragile, rate-limited)
    TavilyProvider      -> api.tavily.com, key chahiye, LLM-friendly JSON (content snippets)

Naya provider (Brave, SerpAPI, Bing, Exa...) add karna ho to bas `search()` implement karo
jo `list[SearchResult]` de. Agent aur tool ko kuch pata nahi chalega. Yahi 'adapter' pattern hai,
jo humne agentkit mein LLM providers ke liye use kiya tha.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; agentic-ai-handbook/0.1; +https://github.com/flow6979/agentic-ai-handbook)"


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict:
        return asdict(self)


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


# ---------------------------------------------------------------- DuckDuckGo (HTML)
class _DDGParser(HTMLParser):
    """DDG ke HTML results page se (title, href, snippet) nikaalta hai.

    Structure (simplified):
      <a class="result__a" href="//duckduckgo.com/l/?uddg=<real-url>">Title</a>
      <a class="result__snippet" ...>Snippet text</a>
    """

    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._field: str | None = None  # "title" ya "snippet" capture ho raha hai

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self.results.append({"title": "", "url": a.get("href", ""), "snippet": ""})
            self._field = "title"
        elif "result__snippet" in classes and self.results:
            self._field = "snippet"

    def handle_endtag(self, tag):
        if tag in ("a", "div", "td"):
            self._field = None

    def handle_data(self, data):
        if self._field and self.results:
            self.results[-1][self._field] += data


def _clean_ddg_url(href: str) -> str:
    """DDG links redirect wrapper hote hain: //duckduckgo.com/l/?uddg=https%3A%2F%2F... -> real url."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href


class DuckDuckGoProvider:
    name = "duckduckgo"
    URL = "https://html.duckduckgo.com/html/"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            r = self.client.post(self.URL, data={"q": query}, headers={"User-Agent": USER_AGENT})
        except httpx.TransportError as e:
            raise SearchError(f"DuckDuckGo network error: {e}") from e
        if r.status_code >= 400:
            raise SearchError(f"DuckDuckGo HTTP {r.status_code}")
        parser = _DDGParser()
        parser.feed(r.text)
        results = [
            SearchResult(" ".join(x["title"].split()), _clean_ddg_url(x["url"]), " ".join(x["snippet"].split()))
            for x in parser.results
            if x["url"] and "duckduckgo.com/y.js" not in x["url"]  # ads skip
        ]
        if not results and ("anomaly" in r.text.lower() or r.status_code == 202):
            raise SearchError("DuckDuckGo blocked the request (bot check / rate limit). Wait or use TAVILY_API_KEY.")
        return results[:max_results]


# ---------------------------------------------------------------- Tavily (API)
class TavilyProvider:
    name = "tavily"
    URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=20)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            r = self.client.post(
                self.URL,
                json={"query": query, "max_results": max_results, "search_depth": "basic"},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.TransportError as e:
            raise SearchError(f"Tavily network error: {e}") from e
        if r.status_code >= 400:
            raise SearchError(f"Tavily HTTP {r.status_code}: {r.text[:200]}")
        return [
            SearchResult(x.get("title", ""), x.get("url", ""), " ".join((x.get("content") or "").split())[:500])
            for x in r.json().get("results", [])
        ][:max_results]


# ---------------------------------------------------------------- helpers
def normalize_url(url: str) -> str:
    """Dedupe ke liye: fragment hatao, trailing slash hatao, host lowercase."""
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", p.query, ""))


def dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen, out = set(), []
    for r in results:
        key = normalize_url(r.url)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def get_search_provider(client: httpx.Client | None = None) -> SearchProvider:
    """Key hai to Tavily (reliable), warna DuckDuckGo (free, fragile)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    key = os.getenv("TAVILY_API_KEY")
    return TavilyProvider(key, client) if key else DuckDuckGoProvider(client)
