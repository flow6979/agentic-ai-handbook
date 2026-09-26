**Language:** [Hinglish](TESTING.md) · English

# Testing: parallelization (code review + moderation)

## Setup
Repo root: `pip install -e ".[all]"`, put `LLM_MODEL` + key in `.env`.

## Run

```bash
python 02-agentic-architectures/03-parallelization/main.py --offline            # both demos
python 02-agentic-architectures/03-parallelization/main.py review               # real LLM, code review only
python 02-agentic-architectures/03-parallelization/main.py moderate
```

## What to look for

```
=== SECTIONING: 3 reviewers in parallel (threads) ===
- security     high   ['SQL built by string concat -> SQL injection...']
- performance  medium ['Orders query inside loop (N+1)...']
overall=request_changes failed=[] took=0.308s (sequential would be ~3x)   <- 3 x 0.3s fake delay, but it took ~0.3s

=== VOTING: 5 moderators ===
'You are an idiot, delete your account'  -> block (unsafe 4/5, invalid 0)
```

- Offline, each fake reviewer sleeps for 0.3s: `took` ~0.3s = proof of parallelism.
- With a real LLM, look at `took` and compare with `max_workers=1` (Tinker #1).
- In voting, `unsafe x/5` = confidence. Pay attention to borderline comments (3/5).

## Offline tests

```bash
pytest 02-agentic-architectures/03-parallelization -v
```
- `test_sectioning_runs_in_parallel` / `test_sectioning_async_matches`: prove parallelism through timing.
- `test_one_failed_reviewer_does_not_kill_the_report`: partial failure handling.
- `test_voting_majority`, `test_voting_threshold_and_invalid_votes`, `test_voting_with_different_models`.

## Tinker with it

1. **Sequential vs parallel**: run `review_code_threads(llm, code, max_workers=1)` with a real LLM; compare the time.
2. **A new aspect**: add a `"testing"` reviewer to `ASPECTS`. Did you have to change anything else in the code? (No: that is the beauty of sectioning.)
3. **Model diversity**: `moderate([get_llm("groq:..."), get_llm("gemini:..."), get_llm("ollama:...")], text)`. How much do the models disagree on borderline comments?
4. **Self-consistency**: build a `solve_math(llm, q)` like `one_vote` that returns the final number, run it 5 times, take the majority. Compare single-call vs majority accuracy on 10 tricky questions.
5. **Simulate rate limits**: moderate 20 comments at once (100 calls). Did you get 429s? Look at the `RetryingLLM` logs, then cap with a semaphore / `max_workers`.
6. **LLM aggregator**: after `aggregate()`, add an LLM call that writes all three reviews up as one PR comment.
