# Testing: parallelization (code review + moderation)

## Setup
Repo root: `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.

## Run

```bash
python 02-agentic-architectures/03-parallelization/main.py --offline            # dono demos
python 02-agentic-architectures/03-parallelization/main.py review               # real LLM, sirf code review
python 02-agentic-architectures/03-parallelization/main.py moderate
```

## Kya dekhna hai

```
=== SECTIONING: 3 reviewers in parallel (threads) ===
- security     high   ['SQL built by string concat -> SQL injection...']
- performance  medium ['Orders query inside loop (N+1)...']
overall=request_changes failed=[] took=0.308s (sequential would be ~3x)   <- 3 x 0.3s fake delay, par ~0.3s laga

=== VOTING: 5 moderators ===
'You are an idiot, delete your account'  -> block (unsafe 4/5, invalid 0)
```

- Offline mein har fake reviewer 0.3s sleep karta hai: `took` ~0.3s = parallel proof.
- Real LLM pe `took` dekho aur `max_workers=1` karke compare karo (Tinker #1).
- Voting mein `unsafe x/5` = confidence. Borderline comments (3/5) pe dhyan do.

## Offline tests

```bash
pytest 02-agentic-architectures/03-parallelization -v
```
- `test_sectioning_runs_in_parallel` / `test_sectioning_async_matches`: timing se parallelism prove.
- `test_one_failed_reviewer_does_not_kill_the_report`: partial failure handling.
- `test_voting_majority`, `test_voting_threshold_and_invalid_votes`, `test_voting_with_different_models`.

## Tinker karo

1. **Sequential vs parallel**: `review_code_threads(llm, code, max_workers=1)` real LLM pe chalao; time compare karo.
2. **Naya aspect**: `ASPECTS` mein `"testing"` reviewer add karo. Code mein kuch aur change karna pada? (Nahi: yahi sectioning ki khoobsurti hai.)
3. **Model diversity**: `moderate([get_llm("groq:..."), get_llm("gemini:..."), get_llm("ollama:...")], text)`. Borderline comments pe models kitna disagree karte hain?
4. **Self-consistency**: `one_vote` jaisa `solve_math(llm, q)` banao jo final number return kare, 5 baar chalao, majority lo. Single call vs majority accuracy compare karo 10 tricky questions pe.
5. **Rate limit simulate**: 20 comments ek saath moderate karo (100 calls). 429 aaye? `RetryingLLM` logs dekho, phir semaphore / `max_workers` se cap karo.
6. **LLM aggregator**: `aggregate()` ke baad ek LLM call add karo jo teeno reviews ko ek PR comment mein likhe.
