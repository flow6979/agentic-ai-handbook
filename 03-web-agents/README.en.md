**Language:** [Hinglish](README.md) · English

# 03 · Web Agents: how an agent brings in data from the internet

An LLM's knowledge stops at a **training cutoff**, and it knows nothing about your live data. To bring in data from the internet, the agent has to be given **tools**. In this section we understand every level of internet access through small projects.

```
                    The agent needs the internet
                               │
      ┌──────────────┬─────────┴────┬───────────────┬─────────────────┐
      ▼              ▼              ▼               ▼                 ▼
 Structured API   Web Search    Page Reader    Deep Research    Real Browser
 (JSON, no HTML)  (what         (extract a     (plan+search+    (JS pages, login,
                   exists?)      URL's text)    read+cite)       clicks, forms)
      │              │              │               │                 │
  01-api-tools   02-web-search  03-web-page-   04-deep-research  05-browser-
                                reader         -agent            automation-concepts

  most reliable ◄─────────────────────────────────────────────────► most flexible
  cheapest                                                           most expensive / fragile
```

**Golden rule:** if an API exists, use it first. Use scraping or a browser only when there is no other way.

## Projects

| # | Project | What you will learn | Key concepts |
|---|---------|--------------|--------------|
| 01 | [api-tools](01-api-tools/) | Turning public APIs into tools (weather, currency, Wikipedia) | timeout, retry/backoff, TTL cache, response trimming, tool design |
| 02 | [web-search](02-web-search/) | Plugging in a search provider + answers with citations | adapter pattern, DuckDuckGo vs Tavily, dedupe, citation verification |
| 03 | [web-page-reader](03-web-page-reader/) | Opening a URL safely and extracting the main content | SSRF guard, robots.txt, HTML extraction, chunking, prompt injection |
| 04 | [deep-research-agent](04-deep-research-agent/) | Building a cited report through multi-step research | plan→search→read→notes→coverage loop, budget, structured outputs |
| 05 | [browser-automation-concepts](05-browser-automation-concepts/) | When and how to use real-browser agents | accessibility tree, DOM vs vision, Playwright, computer-use |

**Order:** 01 → 02 → 03 → 04 (04 reuses the code from 02 and 03) → 05.

## Run everything at once

```bash
# from the repo root (setup: see the root README)
.venv/bin/pytest 03-web-agents                                   # offline tests, no internet/keys
python 03-web-agents/01-api-tools/main.py --offline              # offline demo of each project
python 03-web-agents/04-deep-research-agent/main.py "your topic" # real LLM + real internet
```

Each project has two docs: `CONCEPTS.en.md` (concept + diagrams + code mapping) and `TESTING.en.md` (how to run it, what to look for, tinkering exercises).
