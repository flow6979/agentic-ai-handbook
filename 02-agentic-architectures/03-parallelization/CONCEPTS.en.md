**Language:** [Hinglish](CONCEPTS.md) · English

# Parallelization

## 1. What is the concept?

When parts of a task **don't depend on each other**, run them **at the same time** (concurrently), then
**aggregate** the results (with code or an LLM). There are two main subtypes:

```
 1) SECTIONING  (SPLIT the task, run the different parts in parallel)

                 ┌──► security reviewer ────┐
   code ────────►├──► performance reviewer ─┼──► aggregator ──► report
                 └──► readability reviewer ─┘
       total time ≈ the slowest reviewer   (sequential: the sum of all)


 2) VOTING  (the SAME task N times, majority of the answers)

                 ┌──► moderator 1: unsafe ──┐
   comment ─────►├──► moderator 2: safe   ──┼──► count votes ──► block / allow
                 ├──► moderator 3: unsafe ──┤     (majority or threshold)
                 ├──► moderator 4: unsafe ──┤
                 └──► moderator 5: unsafe ──┘
```

## 2. Sectioning: why?

- **Speed**: 3 LLM calls x 3 sec = 9 sec sequential, ~3 sec parallel.
- **Focus**: one prompt that checks "security + performance + readability" gives each of them only half its attention.
  A separate focused reviewer is better at each aspect (just like in chaining).
- **Isolation**: if one reviewer fails, the others' results survive.

## 3. Voting: why?

- LLMs are **stochastic**: sometimes they give a wrong answer for the same input. A majority of N votes is more **reliable**.
- You get a **confidence signal** for free: 5/5 agree = confident, 3/5 = borderline (human review?).
- **Threshold tuning** controls precision/recall:
  - `block_threshold=1` -> block on even a single unsafe vote (high recall, more false positives)
  - majority (3/5) -> balanced

Where does the diversity for voting come from:
| Diversity source | How | Strength |
|---|---|---|
| Sampling | same prompt, temperature 0.7-1.0 | weak-medium |
| Prompt | different personas / phrasing per voter | medium |
| Model | different providers (Groq Llama + Gemini + GPT) | strong (errors are not correlated) |

**Self-consistency** (a famous technique for reasoning) is also just voting: ask the same maths question N times, take the majority of the final answers.

## 4. Implementation choices (Python)

```
 ThreadPoolExecutor                         asyncio.gather
 ──────────────────                         ──────────────
 simplest in sync code                      natural in an async app (FastAPI)
 LLM call = network wait (IO bound)         best with a native async client
 -> the GIL is not a problem                with a sync client, use asyncio.to_thread
```
Both are in this project. Remember **rate limits**: 50 parallel calls = 429 errors. Cap it with `max_workers`
(or a semaphore), and agentkit's `RetryingLLM` does backoff.

## 5. When to use it / when not

Use it when:
- The subtasks are independent (sectioning).
- You can't trust a single answer and the decision is high-stakes (voting: moderation, grading, classification).
- Latency matters and you can afford parallel calls.

Don't use it when:
- The steps are dependent (B needs A's output) -> chaining.
- The subtasks depend on the input and are not known in advance -> orchestrator-workers (08).
- Cost is tight: voting = N times the cost.

## 6. Production pitfalls

- **Partial failure**: one branch fails -> don't throw away the whole report, but don't "approve" either (a missing review = unsafe). Check `failed_aspects`.
- **Invalid votes**: treat a vote that fails to parse as an "abstain" and leave it out of the count (`invalid`).
- **Rate limits / cost**: cap the parallelism.
- **Correlated errors**: 5 votes from the same model can make the same mistake. Bring in model diversity.
- **An LLM in the aggregation**: if the aggregator is also an LLM, that is one more failure point; aggregate in code wherever you can.

## 7. How this project uses it

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
