**Language:** Hinglish · [English](README.en.md)

# 03 · Web Agents: agent internet se data kaise laaye

LLM ki knowledge ek **training cutoff** pe ruk jaati hai, aur use tumhare live data ka pata nahi hota. Internet se data laane ke liye agent ko **tools** dene padte hain. Is section mein hum internet access ke har level ko chhote projects se samjhenge.

```
                    Agent ko internet chahiye
                               │
      ┌──────────────┬─────────┴────┬───────────────┬─────────────────┐
      ▼              ▼              ▼               ▼                 ▼
 Structured API   Web Search    Page Reader    Deep Research    Real Browser
 (JSON, no HTML)  (kya exist    (URL ka text   (plan+search+    (JS pages, login,
                   karta hai?)   nikaalo)       read+cite)       clicks, forms)
      │              │              │               │                 │
  01-api-tools   02-web-search  03-web-page-   04-deep-research  05-browser-
                                reader         -agent            automation-concepts

  sabse reliable ◄────────────────────────────────────────────────► sabse flexible
  sabse sasta                                                        sabse mehenga / fragile
```

**Golden rule:** agar koi API maujood hai to pehle wahi use karo. Scraping ya browser tabhi use karo jab koi aur raasta na ho.

## Projects

| # | Project | Kya seekhoge | Key concepts |
|---|---------|--------------|--------------|
| 01 | [api-tools](01-api-tools/) | Public APIs ko tools banana (weather, currency, Wikipedia) | timeout, retry/backoff, TTL cache, response trimming, tool design |
| 02 | [web-search](02-web-search/) | Search provider plug karna + citations wala answer | adapter pattern, DuckDuckGo vs Tavily, dedupe, citation verification |
| 03 | [web-page-reader](03-web-page-reader/) | URL safely kholna aur main content nikaalna | SSRF guard, robots.txt, HTML extraction, chunking, prompt injection |
| 04 | [deep-research-agent](04-deep-research-agent/) | Multi-step research se cited report banana | plan→search→read→notes→coverage loop, budget, structured outputs |
| 05 | [browser-automation-concepts](05-browser-automation-concepts/) | Real browser wale agents kab aur kaise | accessibility tree, DOM vs vision, Playwright, computer-use |

**Order:** 01 → 02 → 03 → 04 (04 mein 02 aur 03 ka code reuse hota hai) → 05.

## Sab ek saath chalao

```bash
# repo root se (setup: root README dekho)
.venv/bin/pytest 03-web-agents                                   # offline tests, no internet/keys
python 03-web-agents/01-api-tools/main.py --offline              # har project ka offline demo
python 03-web-agents/04-deep-research-agent/main.py "your topic" # real LLM + real internet
```

Har project mein do docs hain: `CONCEPTS.md` (concept + diagrams + code mapping) aur `TESTING.md` (kaise chalayein, kya dekhein, tinker karne ke exercises).
