**Language:** Hinglish · [English](TESTING.en.md)

# 04 · Deep Research Agent: test aur tinker kaise karein

## 1. Offline demo
```bash
python 03-web-agents/04-deep-research-agent/main.py --offline
```
Trace mein poora research flow dikhta hai:
```
[research:info] plan: ['solar cost trend', 'solar growth 2023', 'solar challenge']
[research:tool] search('solar cost trend') -> 1 results
[research:llm]  1 notes from https://energy.example/solar-cost
...
[research:info] round 1: complete=False missing=['solar storage solutions']   ← gap mila
[research:tool] search('solar storage solutions') -> 1 results                 ← round 2
[research:info] round 2: complete=True
```
Phir cited report aur stats aate hain: `[rounds=2 searches=4/6 pages=4/8 notes=4 skipped=0]`.

## 2. Real run (real LLM + real internet)
```bash
python 03-web-agents/04-deep-research-agent/main.py "State of solid-state batteries in 2026"
python 03-web-agents/04-deep-research-agent/main.py "Pros and cons of Rust vs Go for backend services" \
    --max-searches 4 --max-pages 5 --rounds 2 -o rust_vs_go.md
```
Search DuckDuckGo se hota hai (ya Tavily, agar key ho). Pages 03 ke safe fetcher se padhe jaate hain.

**Kya dekhna hai:**
- Plan ke sub-questions sensible aur searchable hain ya nahi
- `read failed ...` lines: kuch sites 403 dengi ya robots se block karengi. Research phir bhi chalti rahegi.
- Report ke har `[n]` ko `## Sources` mein dhundho aur khol ke check karo ki claim sach mein wahan hai. Yeh manual faithfulness eval hai.
- Cost ka andaza: calls ≈ 1 (plan) + pages (notes) + rounds (coverage) + 1 (report)

## 3. Offline tests
```bash
.venv/bin/pytest 03-web-agents/04-deep-research-agent -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_full_pipeline_iterates_until_coverage_complete` | Gap milne pe 2nd round chalta hai |
| `test_every_citation_number_maps_to_a_source` | Koi `[n]` bina source ke nahi hai |
| `test_source_urls_come_from_pages_read_not_from_llm` | LLM ka fake URL ignore hota hai |
| `test_budget_is_enforced` | Limits kabhi cross nahi hoti |
| `test_failing_page_is_skipped_not_fatal` | Ek page fail hone se research fail nahi hoti |
| `test_no_results_gives_honest_report` | Kuch na mile to honest "no sources" message aata hai, hallucinated report nahi |

## 4. Tinker karo 🔧
1. **Parallel research:** `_investigate` ko sub-questions ke liye `concurrent.futures.ThreadPoolExecutor` se parallel chalao. Budget ko thread-safe banao (`threading.Lock`). Wall-clock time compare karo.
2. **Two-model setup:** `DeepResearcher` mein `extract_llm` (sasta, jaise `groq:llama-3.1-8b-instant`) aur `writer_llm` (achha model) alag karo. Cost vs quality dekho.
3. **Human-in-the-loop plan:** plan banne ke baad `input("Edit plan? ")` se user ko sub-questions edit karne do.
4. **Contradiction detection:** writer se pehle ek step add karo jo notes mein conflicting claims dhundhe aur report mein "Sources disagree" section banaye.
5. **Citation checker:** report ke har sentence ke liye check karo ki usme `[n]` hai ya nahi. Bina citation wale sentences ko flag karo (02 ka `verify_citations` idea).
6. **Domain credibility:** `search()` wrapper mein `.gov`, `.edu` aur known publishers ko upar rakho, aur content farms ko neeche.
