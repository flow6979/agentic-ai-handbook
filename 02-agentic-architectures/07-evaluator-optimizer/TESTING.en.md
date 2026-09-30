**Language:** [Hinglish](TESTING.md) · English

# Testing: evaluator-optimizer (launch tweet polisher)

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + a key in `.env`.
For better results, use different models for the generator and the judge:
```
GEN_MODEL=groq:llama-3.3-70b-versatile
EVAL_MODEL=gemini:gemini-3.8-flash
```

## Run

```bash
python 02-agentic-architectures/07-evaluator-optimizer/main.py --offline
python 02-agentic-architectures/07-evaluator-optimizer/main.py
python 02-agentic-architectures/07-evaluator-optimizer/main.py "Chai Point - office chai delivery in 10 min, Bangalore" --threshold 9
```

## What to look for

```
--- iteration 1 ---
Snapdeploy is a new tool ... #devops #cloud #startup
hard_errors=['too long: 359 chars > 280', 'more than 2 hashtags'] scores={...0...}   <- the judge was never called

--- iteration 2 ---
hard_errors=[] scores={'clarity': 7, 'hook': 3, 'cta': 2}
feedback='Weak hook, no CTA. Lead with the pain.'                                    <- specific feedback

--- iteration 3 ---
Stop babysitting deploys. ...
scores={'clarity': 9, 'hook': 8, 'cta': 8}
STOP: passed
```

- With a real LLM, check: does the score actually go up after feedback? How many iterations does it take?
- If you get `STOP: no_improvement`, see which iteration was the BEST (it's often not the last one).

## Offline tests

```bash
pytest 02-agentic-architectures/07-evaluator-optimizer -v
```
- `test_loop_passes_on_third_iteration`: the hard-fail draft never reached the judge (`len(ev.calls) == 2`), and the feedback went into the next prompt.
- `test_stops_on_no_improvement_and_keeps_best`: scores were dropping -> it stopped, best = v1.
- `test_missing_criterion_counts_as_zero`: the judge skipped `cta` -> 0, so it did not pass.

## Tinker with it

1. **Self-grading bias**: keep `GEN_MODEL` and `EVAL_MODEL` the same vs different. Compare the average iterations and final scores.
2. **New criterion**: add `"tone": "Is it confident but not hypey?"` to `RUBRIC`. Did passing get harder?
3. **Execution-based evaluator**: a new project: the generator writes a Python function, the evaluator runs `pytest` (subprocess), and the failures become the feedback. This is the core loop of coding agents.
4. **Judge calibration**: give the judge 5 known-good and 5 known-bad tweets (few-shot) in the system prompt. Did the spread of scores change?
5. **Threshold vs cost**: note iterations + tokens at `--threshold 6/8/10`. Where do diminishing returns start?
