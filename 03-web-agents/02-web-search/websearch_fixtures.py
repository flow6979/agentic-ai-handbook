"""Offline fixtures: DuckDuckGo jaisa HTML page, Tavily jaisa JSON, aur scripted LLM."""
from __future__ import annotations

import httpx

from agentkit import ScriptedLLM, call, tool_response

DDG_HTML = """
<html><body>
<div class="result results_links">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2Fdownloads%2Frelease%2Fpython-3130%2F&amp;rut=abc">Python Release Python 3.13.0 | Python.org</a>
  </h2>
  <a class="result__snippet" href="#">Python 3.13.0 is the newest major release. It includes a new <b>interactive interpreter</b> and experimental free-threaded mode.</a>
</div>
<div class="result results_links">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Fwhatsnew%2F3.13.html&amp;rut=def">What's New In Python 3.13</a>
  </h2>
  <a class="result__snippet" href="#">This article explains the new features in Python 3.13, compared to 3.12.</a>
</div>
<div class="result results_links">
  <h2 class="result__title">
    <a class="result__a" href="https://duckduckgo.com/y.js?ad_provider=x">Sponsored: Learn Python fast</a>
  </h2>
</div>
<div class="result results_links">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Fwhatsnew%2F3.13.html%23summary&amp;rut=ghi">What's New In Python 3.13 (summary)</a>
  </h2>
  <a class="result__snippet" href="#">Duplicate of the page above with a #fragment.</a>
</div>
</body></html>
"""

DDG_BLOCKED_HTML = "<html><body><div class='anomaly-modal'>Unfortunately, bots use DuckDuckGo too.</div></body></html>"

TAVILY_JSON = {
    "results": [
        {"title": "What's New In Python 3.13", "url": "https://docs.python.org/3/whatsnew/3.13.html",
         "content": "Python 3.13 adds a new interactive interpreter, experimental free-threaded build and a JIT."},
    ]
}


def mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "html.duckduckgo.com":
        return httpx.Response(200, text=DDG_HTML)
    if request.url.host == "api.tavily.com":
        return httpx.Response(200, json=TAVILY_JSON)
    return httpx.Response(404)


def offline_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(mock_handler))


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM([
        tool_response(call("web_search", query="python 3.13 new features")),
        "Python 3.13 brings a new interactive interpreter (REPL) and an experimental free-threaded "
        "(no-GIL) mode [1].\n\nSources:\n[1] https://docs.python.org/3/whatsnew/3.13.html\n"
        "[2] https://www.python.org/downloads/release/python-3130/",
    ])
