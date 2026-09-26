**Language:** [Hinglish](TESTING.md) · English

# 04 · Deep Research Agent: how to test and tinker

## 1. Offline demo
```bash
python 03-web-agents/04-deep-research-agent/main.py --offline
```
The trace shows the whole research flow:
```
[research:info] plan: ['solar cost trend', 'solar growth 2023', 'solar challenge']
[research:tool] search('solar cost trend') -> 1 results
[research:llm]  1 notes from https://energy.example/solar-cost
...
[research:info] round 1: complete=False missing=['solar storage solutions']   ← a gap was found
[research:tool] search('solar storage solutions') -> 1 results                 ← round 2
[research:info] round 2: complete=True
```
Then the cited report and the stats: `[rounds=2 searches=4/6 pages=4/8 notes=4 skipped=0]`.

## 2. Real run (real LLM + real internet)
```bash
python 03-web-agents/04-deep-research-agent/main.py "State of solid-state batteries in 2026"
python 03-web-agents/04-deep-research-agent/main.py "Pros and cons of Rust vs Go for backend services" \
    --max-searches 4 --max-pages 5 --rounds 2 -o rust_vs_go.md
```
Search goes through DuckDuckGo (or Tavily, if you have a key). Pages are read with the safe fetcher from 03.

**What to look for:**
- Whether the plan's sub-questions are sensible and searchable
- `read failed ...` lines: some sites return 403 or block via robots. The research keeps going anyway.
- Find each `[n]` of the report in `## Sources`, open it and check that the claim is really there. This is a manual faithfulness eval.
- Estimating cost: calls ≈ 1 (plan) + pages (notes) + rounds (coverage) + 1 (report)

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/04-deep-research-agent -v
```
| Test | What it proves |
|---|---|
| `test_full_pipeline_iterates_until_coverage_complete` | A 2nd round runs when a gap is found |
| `test_every_citation_number_maps_to_a_source` | No `[n]` without a source |
| `test_source_urls_come_from_pages_read_not_from_llm` | The LLM's fake URL is ignored |
| `test_budget_is_enforced` | The limits are never crossed |
| `test_failing_page_is_skipped_not_fatal` | One failing page does not fail the research |
| `test_no_results_gives_honest_report` | If nothing is found you get an honest "no sources" message, not a hallucinated report |

## 4. Tinker 🔧
1. **Parallel research:** run `_investigate` for the sub-questions in parallel with `concurrent.futures.ThreadPoolExecutor`. Make the budget thread-safe (`threading.Lock`). Compare wall-clock time.
2. **Two-model setup:** split `DeepResearcher` into an `extract_llm` (cheap, for example `groq:llama-3.1-8b-instant`) and a `writer_llm` (a good model). Look at cost vs quality.
3. **Human-in-the-loop plan:** after the plan is built, let the user edit the sub-questions with `input("Edit plan? ")`.
4. **Contradiction detection:** add a step before the writer that looks for conflicting claims in the notes and creates a "Sources disagree" section in the report.
5. **Citation checker:** for each sentence of the report, check whether it has a `[n]`. Flag sentences without a citation (the `verify_citations` idea from 02).
6. **Domain credibility:** in a `search()` wrapper, rank `.gov`, `.edu` and known publishers higher, and content farms lower.
