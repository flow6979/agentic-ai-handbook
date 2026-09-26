**Language:** [Hinglish](CONCEPTS.md) · English

# 01 · API Tools: turning public APIs into agent tools

## The concept, from scratch

An LLM cannot go on the internet by itself. It only generates text. "Internet access" means **we give it a Python function (a tool) that calls an API**, and the LLM decides when to call it and with which arguments.

```
 User: "Weather in Paris + how many EUR is 500 USD?"
        │
        ▼
 ┌─────────────┐   tool_call: get_weather(city="Paris")         ┌──────────────┐
 │    LLM      │ ──────────────────────────────────────────────►│  Our Python  │──► open-meteo API
 │ (decides)   │   tool_call: convert_currency(500,"USD","EUR") │  tool code   │──► frankfurter API
 │             │ ◄──────────────────────────────────────────────│ (executes)   │
 └─────────────┘   results (small JSON)                          └──────────────┘
        │
        ▼
 "Paris 18°C, partly cloudy... 500 USD ≈ 427 EUR"
```

A structured (JSON) API is the **most reliable** way to bring in data from the internet:
- The data is clean, with no HTML junk
- The format is stable; a website redesign breaks nothing
- It is often free or cheap, and allowed under the terms of service

## Production problems and their solutions

The internet is unreliable. This is the difference between a "demo" tool and a "production" tool:

```
tool call
   │
   ▼
┌──────────┐  hit   ┌──────────────┐
│  cache?  │──────► │ cached value │──► return (0 ms, free)
└────┬─────┘        └──────────────┘
     │ miss
     ▼
┌──────────────────────┐
│ HTTP GET (timeout=10s)│
└────┬─────────────────┘
     │
     ├── 200 ──────────► cache.set() ──► trim ──► return
     ├── 429 / 5xx / timeout ──► wait 0.5s, 1s, 2s... ──► retry (max N)
     └── 400 / 404 ────────► ApiError immediately (retrying is pointless)
                                  │
                                  ▼
                      The agent loop gives the LLM an "ERROR: ..." string;
                      the LLM tells the user or takes another route
```

| Problem | Solution | Why |
|---|---|---|
| The API hangs | **timeout** | Otherwise the agent waits forever |
| 429 rate limit, 503 overload | **retry + exponential backoff** | Temporary errors usually clear up on the next try |
| 404 / 400 | **no retry**, error immediately | Retrying bad input will not make it right |
| The same question again and again | **TTL cache** | Saves latency and money, and keeps you under rate limits |
| The API returned 20 KB of JSON | **trim + only the needed fields** | The context window is expensive, and too much text confuses the model |
| The tool crashed | **give the error string to the LLM** | The LLM can recover, whereas a crashed agent gives the user nothing |

### Rules for good tool design
1. **One tool = one user-level task.** `get_weather(city)` does both the geocode and the forecast calls internally. If you make the LLM do 2 steps, both the chance of mistakes and the token cost go up.
2. **The docstring is the tool's prompt.** A line like "Use this first when you don't know the exact title" tells the LLM *when* to use the tool.
3. **Keep output human-readable and small:** write `sky: "partly cloudy"`, not `weather_code: 2`.
4. **Give a helpful message on bad input:** instead of crashing, return `"No location found for 'Atlantis'. Try the English name."`.
5. **Dependency injection:** in `make_tools(api)` the client comes from outside. A fake client in tests, the real client in production.

### Subtypes: how many kinds of API tools are there

```
API tools
 ├─ No-key public APIs      → Wikipedia, open-meteo, frankfurter   (this project)
 ├─ API-key APIs            → OpenWeather, NewsAPI, GitHub          (key in .env, send it in a header)
 ├─ OAuth APIs (user's data)→ Gmail, Google Calendar, Slack         (user consent + token refresh)
 ├─ Internal company APIs   → orders DB, CRM                        (auth + permissions matter most)
 └─ GraphQL APIs            → one endpoint, pick fields in the query (less over-fetching)
```

## When to use it / when not to
- ✅ When an official API exists for the data (weather, stocks, maps, GitHub, internal services)
- ✅ When you need structured, reliable numbers
- ❌ When there is no API and the data is only on a web page: see 03-web-page-reader
- ❌ When you do not even know where the data is: see 02-web-search

## Pitfalls
- **The LLM "guesses" a number:** write "Never guess numbers, use tools" in the system prompt.
- **The cache goes stale:** a 5 min TTL is fine for weather but far too long for a stock price. Pick the TTL from the nature of the data.
- **Rate limits:** free APIs have limits. You need both caching and backoff.
- **User-Agent:** APIs like Wikipedia require a descriptive User-Agent, otherwise they block you.

## How it is used in this project

| Concept | File / function |
|---|---|
| Timeout, retry, backoff, stats | `apitools_http.py` → `ApiClient.get_json()` |
| TTL cache (injectable clock) | `apitools_http.py` → `TTLCache` |
| Response trimming | `apitools_http.py` → `trim()` |
| 4 tools (Wikipedia ×2, weather, currency) | `apitools_tools.py` → `make_tools(api)` |
| Combining 2 API calls into 1 tool | `apitools_tools.py` → `get_weather()` |
| Fake APIs (MockTransport) + scripted LLM | `apitools_fixtures.py` |
| Agent + system prompt ("never guess numbers") | `main.py` → `SYSTEM`, `Agent(...)` |
| Parallel tool calls (weather + currency in one step) | `apitools_fixtures.py` → first response of `offline_llm()` |
