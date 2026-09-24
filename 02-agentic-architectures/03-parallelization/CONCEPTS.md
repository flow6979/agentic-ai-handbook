# Parallelization

## 1. Concept kya hai?

Jab kaam ke hisse ek doosre pe **depend nahi karte**, unhe **ek saath** (concurrently) chalao, phir results
**aggregate** karo (code se ya LLM se). Do main subtypes hain:

```
 1) SECTIONING  (kaam ko TODO, alag alag hisse parallel)

                 ┌──► security reviewer ────┐
   code ────────►├──► performance reviewer ─┼──► aggregator ──► report
                 └──► readability reviewer ─┘
       total time ≈ sabse slow reviewer   (sequential: sabka sum)


 2) VOTING  (SAME kaam N baar, answers ka majority)

                 ┌──► moderator 1: unsafe ──┐
   comment ─────►├──► moderator 2: safe   ──┼──► count votes ──► block / allow
                 ├──► moderator 3: unsafe ──┤     (majority ya threshold)
                 ├──► moderator 4: unsafe ──┤
                 └──► moderator 5: unsafe ──┘
```

## 2. Sectioning: kyun?

- **Speed**: 3 LLM calls x 3 sec = 9 sec sequential, ~3 sec parallel.
- **Focus**: ek prompt jo "security + performance + readability" teeno dekhe, woh sabko aadha-aadha dekhta hai.
  Alag focused reviewer har aspect pe better hota hai (jaise chaining mein).
- **Isolation**: ek reviewer fail ho to baaki ka result bacha rehta hai.

## 3. Voting: kyun?

- LLM **stochastic** hai: same input pe kabhi galat jawab. N votes ka majority zyada **reliable**.
- **Confidence signal** free mein: 5/5 agree = confident, 3/5 = borderline (human review?).
- **Threshold tuning** se precision/recall control:
  - `block_threshold=1` -> ek bhi unsafe vote pe block (high recall, zyada false positives)
  - majority (3/5) -> balanced

Voting ki diversity kahan se aaye:
| Diversity source | Kaise | Strength |
|---|---|---|
| Sampling | same prompt, temperature 0.7-1.0 | weak-medium |
| Prompt | alag personas / phrasing per voter | medium |
| Model | alag providers (Groq Llama + Gemini + GPT) | strong (errors correlated nahi) |

**Self-consistency** (reasoning ke liye famous technique) bhi voting hi hai: same maths question N baar, final answers ka majority.

## 4. Implementation choices (Python)

```
 ThreadPoolExecutor                         asyncio.gather
 ──────────────────                         ──────────────
 sync code mein simplest                    async app (FastAPI) mein natural
 LLM call = network wait (IO bound)         native async client ho to best
 -> GIL problem nahi                        sync client ho to asyncio.to_thread
```
Dono is project mein hain. **Rate limits** yaad rakho: 50 parallel calls = 429 errors. `max_workers` se cap karo
(ya semaphore), aur agentkit ka `RetryingLLM` backoff karta hai.

## 5. Kab use karein / kab nahi

Use karo:
- Subtasks independent hain (sectioning).
- Ek answer pe bharosa nahi, high-stakes decision (voting: moderation, grading, classification).
- Latency matter karti hai aur parallel calls afford kar sakte ho.

Mat karo:
- Steps dependent hain (B ko A ka output chahiye) -> chaining.
- Subtasks input pe depend karte hain, pehle se pata nahi -> orchestrator-workers (08).
- Cost tight hai: voting = N guna cost.

## 6. Production pitfalls

- **Partial failure**: ek branch fail -> poora report mat phenko, lekin "approve" bhi mat karo (missing review = unsafe). `failed_aspects` dekho.
- **Invalid votes**: parse fail wale vote ko "abstain" maano, count mein mat lo (`invalid`).
- **Rate limits / cost**: parallelism cap karo.
- **Correlated errors**: same model ke 5 votes ek jaisi galti kar sakte hain. Model diversity lao.
- **Aggregation mein LLM**: agar aggregator bhi LLM hai to woh ek aur failure point hai; jahan ho sake code se aggregate karo.

## 7. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Sectioning (threads) | `parallel_sectioning.py` -> `review_code_threads()` (ThreadPoolExecutor) |
| Sectioning (asyncio) | `review_code_async()` -> `asyncio.gather` + `asyncio.to_thread` |
| Focused sub-prompts | `ASPECTS` dict, `review_aspect()` |
| Code-based aggregation + partial failure | `aggregate()` -> missing aspect = `request_changes` |
| Voting (N samples, temperature 0.8) | `parallel_voting.py` -> `moderate()`, `one_vote()` |
| Threshold policy | `moderate(block_threshold=...)` |
| Model diversity voting | `moderate([llm1, llm2, llm3], ...)` |
| Speedup proof | `test_sectioning_runs_in_parallel` (3 x 0.2s < 0.5s) |
