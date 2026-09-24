# 01 · API Tools: public APIs ko agent ke tools banana

## Concept, bilkul shuru se

LLM khud internet pe nahi ja sakta. Woh sirf text generate karta hai. "Internet access" ka matlab hota hai ki **hum ek Python function (tool) dete hain jo API call karta hai**, aur LLM decide karta hai ki kab aur kin arguments ke saath use call karna hai.

```
 User: "Paris ka weather + 500 USD kitne EUR?"
        │
        ▼
 ┌─────────────┐   tool_call: get_weather(city="Paris")         ┌──────────────┐
 │    LLM      │ ──────────────────────────────────────────────►│  Our Python  │──► open-meteo API
 │ (decides)   │   tool_call: convert_currency(500,"USD","EUR") │  tool code   │──► frankfurter API
 │             │ ◄──────────────────────────────────────────────│ (executes)   │
 └─────────────┘   results (chhota JSON)                         └──────────────┘
        │
        ▼
 "Paris 18°C, partly cloudy... 500 USD ≈ 427 EUR"
```

Structured API (JSON) internet se data laane ka **sabse reliable** tareeka hai:
- Data clean hota hai, usme HTML ka kachra nahi hota
- Format stable rehta hai, website redesign se kuch nahi tootta
- Aksar free ya sasta hota hai, aur terms of service ke hisaab se allowed bhi

## Production problems aur unke solutions

Internet unreliable hai. Ek "demo" tool aur ek "production" tool mein yahi farak hota hai:

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
     └── 400 / 404 ────────► ApiError turant (retry bekaar hai)
                                  │
                                  ▼
                      Agent loop "ERROR: ..." string LLM ko deta hai,
                      LLM user ko batata hai ya doosra raasta leta hai
```

| Problem | Solution | Kyun |
|---|---|---|
| API hang ho gayi | **timeout** | Warna agent hamesha ke liye ruk jayega |
| 429 rate limit, 503 overload | **retry + exponential backoff** | Temporary errors aksar dusri try pe theek ho jaate hain |
| 404 / 400 | **retry nahi**, turant error | Galat input retry karne se sahi nahi hoga |
| Same sawaal baar baar | **TTL cache** | Latency aur paisa bachta hai, rate limit se bhi bachte ho |
| API ne 20 KB JSON diya | **trim + sirf zaroori fields** | Context window mehenga hai, aur zyada text se model confuse hota hai |
| Tool crash hua | **error string LLM ko do** | LLM recover kar sakta hai, jabki agent crash karega to user ko kuch nahi milega |

### Achhe tool design ke rules
1. **Ek tool = ek user-level kaam.** `get_weather(city)` andar hi andar geocode + forecast, dono calls kar leta hai. Agar LLM se 2 steps karwaoge to galti ka chance aur token cost dono badhenge.
2. **Docstring hi tool ka prompt hai.** "Use this first when you don't know the exact title" jaisi line LLM ko batati hai ki tool *kab* use karna hai.
3. **Output human-readable aur chhota rakho:** `sky: "partly cloudy"` likho, `weather_code: 2` nahi.
4. **Galat input pe helpful message do:** crash ki jagah `"No location found for 'Atlantis'. Try the English name."`.
5. **Dependency injection:** `make_tools(api)` mein client bahar se aata hai. Tests mein fake client, production mein real client.

### Subtypes: API tools ke kitne tarah hote hain

```
API tools
 ├─ No-key public APIs      → Wikipedia, open-meteo, frankfurter   (yeh project)
 ├─ API-key APIs            → OpenWeather, NewsAPI, GitHub          (key .env mein, header mein bhejo)
 ├─ OAuth APIs (user ka data)→ Gmail, Google Calendar, Slack        (user consent + token refresh)
 ├─ Internal company APIs   → orders DB, CRM                        (auth + permissions sabse zaroori)
 └─ GraphQL APIs            → ek endpoint, query mein fields chuno  (over-fetching kam)
```

## Kab use karein / kab nahi
- ✅ Jab data ka koi official API maujood ho (weather, stocks, maps, GitHub, internal services)
- ✅ Jab structured, reliable numbers chahiye
- ❌ Jab API nahi hai aur data sirf webpage pe hai: 03-web-page-reader dekho
- ❌ Jab pata hi nahi ki data kahan hai: 02-web-search dekho

## Pitfalls
- **LLM number "guess" kar leta hai:** system prompt mein "Never guess numbers, use tools" likho.
- **Cache stale ho jata hai:** weather ke liye 5 min TTL theek hai, stock price ke liye bahut lamba hai. TTL data ke nature se tay karo.
- **Rate limits:** free APIs ke limits hote hain. Cache aur backoff dono zaroori hain.
- **User-Agent:** Wikipedia jaise APIs descriptive User-Agent maangte hain, warna block kar dete hain.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Timeout, retry, backoff, stats | `apitools_http.py` → `ApiClient.get_json()` |
| TTL cache (injectable clock) | `apitools_http.py` → `TTLCache` |
| Response trimming | `apitools_http.py` → `trim()` |
| 4 tools (Wikipedia ×2, weather, currency) | `apitools_tools.py` → `make_tools(api)` |
| 2 API calls ko 1 tool mein milana | `apitools_tools.py` → `get_weather()` |
| Fake APIs (MockTransport) + scripted LLM | `apitools_fixtures.py` |
| Agent + system prompt ("never guess numbers") | `main.py` → `SYSTEM`, `Agent(...)` |
| Parallel tool calls (weather + currency ek step mein) | `apitools_fixtures.py` → `offline_llm()` pehla response |
