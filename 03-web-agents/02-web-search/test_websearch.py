import httpx
import pytest

from agentkit import Agent, NullTracer
from websearch_fixtures import DDG_BLOCKED_HTML, offline_client, offline_llm
from websearch_providers import (DuckDuckGoProvider, SearchError, SearchResult, TavilyProvider, _clean_ddg_url,
                                 dedupe, get_search_provider)
from websearch_tools import SearchLog, make_search_tool, verify_citations


def test_ddg_parser_extracts_real_urls_and_skips_ads():
    results = DuckDuckGoProvider(offline_client()).search("python 3.13")
    urls = [r.url for r in results]
    assert urls[0] == "https://www.python.org/downloads/release/python-3130/"
    assert not any("y.js" in u for u in urls)
    assert "interactive interpreter" in results[0].snippet


def test_clean_ddg_url_passthrough():
    assert _clean_ddg_url("https://example.com/a") == "https://example.com/a"


def test_ddg_block_page_raises_clear_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(202, text=DDG_BLOCKED_HTML)))
    with pytest.raises(SearchError, match="blocked"):
        DuckDuckGoProvider(client).search("x")


def test_tavily_normalizes_to_same_shape():
    from websearch_fixtures import mock_handler

    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        return mock_handler(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = TavilyProvider("tvly-test", client).search("python")
    assert seen["auth"] == "Bearer tvly-test"
    assert isinstance(results[0], SearchResult) and results[0].url.startswith("https://docs.python.org")


def test_dedupe_ignores_fragment_www_and_trailing_slash():
    rs = [SearchResult("a", "https://www.x.com/p/", ""), SearchResult("b", "https://x.com/p#top", "")]
    assert len(dedupe(rs)) == 1


def test_provider_selection(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    assert get_search_provider().name == "duckduckgo"
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert get_search_provider().name == "tavily"


def test_search_tool_dedupes_and_logs():
    log = SearchLog()
    t = make_search_tool(DuckDuckGoProvider(offline_client()), log)
    out = t.fn(query="python 3.13")
    assert out.count("url:") == 2  # 4 raw results: 1 ad skipped, 1 duplicate removed
    assert log.queries == ["python 3.13"]


def test_verify_citations_flags_made_up_urls():
    log = SearchLog()
    log.results = [SearchResult("t", "https://docs.python.org/3/whatsnew/3.13.html", "")]
    check = verify_citations("See https://docs.python.org/3/whatsnew/3.13.html and https://fake.dev/x.", log)
    assert check["verified"] == ["https://docs.python.org/3/whatsnew/3.13.html"]
    assert check["unverified"] == ["https://fake.dev/x"]


def test_agent_answers_with_verified_citations():
    log = SearchLog()
    res = Agent(offline_llm(), [make_search_tool(DuckDuckGoProvider(offline_client()), log)],
                tracer=NullTracer()).run("python 3.13?")
    check = verify_citations(res.output, log)
    assert check["has_citations"] and not check["unverified"]
