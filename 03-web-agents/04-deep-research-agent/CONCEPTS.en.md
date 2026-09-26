**Language:** [Hinglish](CONCEPTS.md) · English

# 04 · Deep Research Agent: plan, search, read, notes, cited report

## Concept

Doing one search and answering is a "quick lookup". **Deep research** is different: a big topic, many angles, and 10+ sources to read, the way an analyst works. The "Deep Research" features of ChatGPT/Gemini/Perplexity follow this pattern.

There are two approaches:
```
 A) Free-form ReAct agent                  B) Structured research workflow (this project)
 ─────────────────────────                 ─────────────────────────────────────────────
 LLM + [search, read] tools,               Code controls the flow. At each step the LLM
 decides by itself in a loop.              does one small, focused job.

 + flexible                                + predictable cost (budget)
 - unpredictable cost, can get             + every step is testable
   stuck in a loop, messy citations        + code tracks the citations (not the LLM)
                                           - less flexible
```
In production **B** is used most often, or a hybrid (B's skeleton, with A inside some steps).

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
          ┌────────────── for each sub-question ─────────────────┐
          │  search(q) ──► top results ──► already seen? skip     │
          │                   │                                   │
          │                   ▼   (budget: pages)                 │
          │             read(url, q) ── fail? skip, log, continue │
          │                   │                                   │
          │                   ▼                                   │
          │   EXTRACT NOTES (llm_json → Notes)                    │
          │   note.source_url = url   ← set by code, not the LLM  │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
                   ┌──────────────────────────────┐
                   │ COVERAGE (llm_json)          │  complete? ──yes──┐
                   │ "what are the gaps?"         │                   │
                   └──────────────┬───────────────┘                   │
                                  │ no: missing = ["solar storage"]   │
                                  └──► next round (up to max_rounds)  │
                                                                      ▼
                   ┌──────────────────────────────────────────────────┐
                   │ WRITE REPORT: from numbered notes [1]..[n]        │
                   │ + code appends the "## Sources" list              │
                   └──────────────────────────────────────────────────┘
```

## Key ideas

### 1. Structured outputs at every step
Every LLM step returns a Pydantic model (`Plan`, `Notes`, `Coverage`), so there is no free text to parse. `agentkit.llm_json` extracts the JSON, validates it, and if it is wrong shows the model the error and retries (self-correction).

### 2. Budget = cost control
Research is never "finished"; every page opens new questions. So there are hard limits:
```python
Budget(max_searches=6, max_pages=8, max_rounds=2)
```
When the budget runs out, the report is built from whatever notes exist (graceful degradation).

### 3. Provenance: code tracks the citations
The most common mistake is having the LLM write the source URL, because it invents URLs. Here a note's `source_url` is **always the URL we actually read**. The fixture LLM deliberately says `i-made-this-up.example`, and a test proves it is ignored.

### 4. Iterative deepening (reflection)
The coverage step is a small "reflection": the model looks at its collected notes and names the gaps, and the next round focuses only on those gaps. This uses the Reflection/Evaluator-Optimizer pattern from section 02.

### 5. Failure isolation
If one page times out or one search fails, the rest of the research keeps going. The reason is recorded in the `skipped` list.

### 6. Dependency injection
In `DeepResearcher(llm, search, read)`, search and read are just functions:
- a fake index in tests
- in `main.py`, `get_search_provider()` from 02 and `PageFetcher` + `top_chunks` from 03

## Subtypes / variations
| Variation | Idea |
|---|---|
| **Single-agent structured** (this one) | One pipeline, the LLM at each step |
| **Multi-agent research** | Planner, parallel researchers (one per sub-question), writer, critic (section 06) |
| **Parallel fan-out** | Search the sub-questions at the same time (asyncio/threads). Lower latency (section 02, parallelization) |
| **STORM-style** | First generate questions from multiple "perspectives" (expert personas), then an outline, then the article |
| **Human-in-the-loop** | Show the plan to the user, start research only after approval |

## Pitfalls
- **Source quality:** SEO spam and AI-generated pages show up in search too. You can add a domain allowlist or credibility scoring.
- **Contradictions:** two sources may give different numbers. Cite both in the report, do not hide it.
- **Context overflow:** with too many notes the writer prompt can overflow. Dedupe or summarize the notes.
- **Cost:** every page costs one LLM call (notes extraction). 8 pages = 8 calls + plan + coverage + report. You can use a cheap model for extraction and a good model for writing.

## How it is used in this project

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
