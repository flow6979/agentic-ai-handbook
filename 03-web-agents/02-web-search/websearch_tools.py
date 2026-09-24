"""Search provider -> agent tool, aur citations ko verify karne ka helper.

Search tool ka output LLM ke liye format kiya gaya hai: har result ka URL saaf likha hai
taaki model usi URL ko cite kare. Phir `verify_citations` check karta hai ki answer mein
jo URLs hain woh sach mein search results mein aaye the (hallucinated links pakadne ke liye).
"""
from __future__ import annotations

import re

from agentkit import Tool, tool

from websearch_providers import SearchProvider, SearchResult, dedupe, normalize_url


class SearchLog:
    """Agent ne jo bhi results dekhe unka record: citations verify karne ke liye."""

    def __init__(self):
        self.results: list[SearchResult] = []
        self.queries: list[str] = []

    def seen_urls(self) -> set[str]:
        return {normalize_url(r.url) for r in self.results}


def make_search_tool(provider: SearchProvider, log: SearchLog | None = None, max_results: int = 5) -> Tool:
    log = log if log is not None else SearchLog()

    @tool
    def web_search(query: str) -> str:
        """Search the web. Returns results with title, url and snippet.
        Use short keyword queries. Search again with different words if results are poor."""
        results = dedupe(provider.search(query, max_results=max_results))
        log.queries.append(query)
        log.results.extend(results)
        if not results:
            return f"No results for {query!r}. Try different keywords."
        return "\n\n".join(f"- title: {r.title}\n  url: {r.url}\n  snippet: {r.snippet}" for r in results)

    return web_search


_URL = re.compile(r"https?://[^\s\)\]>\"']+")


def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,;") for u in _URL.findall(text)]


def verify_citations(answer: str, log: SearchLog) -> dict:
    """Answer ke URLs ko 2 buckets mein baanto: jo search mein aaye (ok) aur jo nahi (suspicious)."""
    seen = log.seen_urls()
    cited = extract_urls(answer)
    ok = [u for u in cited if normalize_url(u) in seen]
    unknown = [u for u in cited if normalize_url(u) not in seen]
    return {"cited": cited, "verified": ok, "unverified": unknown, "has_citations": bool(cited)}
