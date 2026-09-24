# 04 · Deep Research Agent: plan, search, read, notes, cited report

## Concept

Ek search karke answer dena "quick lookup" hai. **Deep research** alag cheez hai: bada topic ho, kai angles ho, aur 10+ sources padhne padein, jaise ek analyst karta hai. ChatGPT/Gemini/Perplexity ke "Deep Research" features yahi pattern follow karte hain.

Do tareeke hain:
```
 A) Free-form ReAct agent                  B) Structured research workflow (yeh project)
 ─────────────────────────                 ─────────────────────────────────────────────
 LLM + [search, read] tools,               Code flow control karta hai. LLM har step pe
 loop mein khud decide kare.               ek chhota, focused kaam karta hai.

 + flexible                                + predictable cost (budget)
 - cost unpredictable, loop mein           + har step testable
   atak sakta hai, citations messy         + citations code track karta hai (LLM nahi)
                                           - kam flexible
```
Production mein aksar **B** use hota hai, ya hybrid (B ka skeleton, aur kuch steps ke andar A).

## Flow

```
                 topic: "Solar power: cost, growth, challenges"
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │ PLAN (llm_json → Plan)       │  "solar cost trend",
                   │ 3-5 searchable sub-questions │  "solar growth 2023", "solar challenge"
                   └──────────────┬───────────────┘
                                  ▼
          ┌────────────── har sub-question ke liye ──────────────┐
          │  search(q) ──► top results ──► already seen? skip     │
          │                   │                                   │
          │                   ▼   (budget: pages)                 │
          │             read(url, q) ── fail? skip, log, continue │
          │                   │                                   │
          │                   ▼                                   │
          │   EXTRACT NOTES (llm_json → Notes)                    │
          │   note.source_url = url   ← code set karta hai, LLM nahi│
          └───────────────────────────┬───────────────────────────┘
                                      ▼
                   ┌──────────────────────────────┐
                   │ COVERAGE (llm_json)          │  complete? ──yes──┐
                   │ "gaps kya hain?"             │                   │
                   └──────────────┬───────────────┘                   │
                                  │ no: missing = ["solar storage"]   │
                                  └──► next round (max_rounds tak)    │
                                                                      ▼
                   ┌──────────────────────────────────────────────────┐
                   │ WRITE REPORT: numbered notes [1]..[n] se          │
                   │ + "## Sources" list code append karta hai         │
                   └──────────────────────────────────────────────────┘
```

## Key ideas

### 1. Structured outputs har step pe
Har LLM step ek Pydantic model return karta hai (`Plan`, `Notes`, `Coverage`), isliye free text parse nahi karna padta. `agentkit.llm_json` JSON nikaalta hai, validate karta hai, aur galat ho to model ko error dikha ke retry karta hai (self-correction).

### 2. Budget = cost control
Research kabhi "khatam" nahi hoti, har page naye sawaal kholta hai. Isliye hard limits:
```python
Budget(max_searches=6, max_pages=8, max_rounds=2)
```
Budget khatam hone pe jo notes hain unhi se report banti hai (graceful degradation).

### 3. Provenance: citations code track karta hai
Sabse common galti hoti hai LLM se source URL likhwana, kyunki woh URL bana deta hai. Yahan note ka `source_url` **hamesha woh URL hai jo humne sach mein padha**. Fixture LLM jaanbujh ke `i-made-this-up.example` bolta hai, aur test prove karta hai ki woh ignore hota hai.

### 4. Iterative deepening (reflection)
Coverage step ek chhota "reflection" hai: model apne collected notes dekh ke gaps batata hai, aur agla round sirf un gaps pe focus karta hai. Yeh section 02 ke Reflection/Evaluator-Optimizer pattern ka use hai.

### 5. Failure isolation
Ek page timeout hua, ya ek search fail hua, to baaki research chalti rehti hai. `skipped` list mein reason record hota hai.

### 6. Dependency injection
`DeepResearcher(llm, search, read)` mein search aur read sirf functions hain:
- tests mein fake index
- `main.py` mein 02 ka `get_search_provider()` aur 03 ka `PageFetcher` + `top_chunks`

## Subtypes / variations
| Variation | Idea |
|---|---|
| **Single-agent structured** (yeh) | Ek pipeline, har step pe LLM |
| **Multi-agent research** | Planner, parallel researchers (har sub-question ke liye ek), writer, critic (section 06) |
| **Parallel fan-out** | Sub-questions ek saath search karo (asyncio/threads). Latency kam hoti hai (section 02, parallelization) |
| **STORM-style** | Pehle multiple "perspectives" (expert personas) se questions generate karo, phir outline, phir article |
| **Human-in-the-loop** | Plan user ko dikhao, approve hone ke baad research shuru karo |

## Pitfalls
- **Source quality:** SEO spam aur AI-generated pages bhi search mein aate hain. Domain allowlist ya credibility scoring add kar sakte ho.
- **Contradictions:** do sources alag numbers de sakte hain. Report mein dono cite karo, chupao mat.
- **Context overflow:** notes bahut ho jaayein to writer prompt overflow ho sakta hai. Notes ko dedupe ya summarize karo.
- **Cost:** har page pe ek LLM call hoti hai (notes extraction). 8 pages = 8 calls + plan + coverage + report. Sasta model extraction ke liye aur achha model writing ke liye use kar sakte ho.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Structured step outputs | `deepresearch_agent.py` → `Plan`, `Notes`, `Coverage` + `llm_json` |
| Budget | `Budget` dataclass, `can_search()` / `can_read()` |
| Plan → investigate → coverage → report loop | `DeepResearcher.run()` |
| Search + read + extract per sub-question | `DeepResearcher._investigate()` |
| Provenance (code sets `source_url`) | `_investigate()` → `n.source_url = url` |
| Seen-URL dedupe, failure skip | `_investigate()` → `seen`, `skipped` |
| Numbered citations + Sources list | end of `run()` |
| Reuse of 02/03 code | `main.py` → `real_tools()` |
| Deterministic fake LLM (routes by `TASK:` marker) | `deepresearch_fixtures.py` → `_responder()` |
