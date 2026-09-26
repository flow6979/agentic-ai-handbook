**Language:** [Hinglish](CONCEPTS.md) · English

# Evaluator-Optimizer

## 1. What is the concept?

Two roles: a **Generator** (writes) and an **Evaluator** (judges against a rubric and gives specific feedback).
The feedback goes back to the generator, which improves the draft. The loop runs until the quality bar is met
or the budget runs out. Exactly like a writer and an editor.

```
            ┌───────────────────────────────────────────────────────────────┐
            │                                                               │
   brief ──►│ GENERATOR ──► draft ──► HARD CHECKS ──fail──┐                 │
            │    ▲                    (code: <=280 chars, │                 │
            │    │                     <=2 hashtags)      │                 │
            │    │                         │ pass         │                 │
            │    │                         ▼              │                 │
            │    │                    EVALUATOR (LLM)     │                 │
            │    │                    rubric: clarity,    │                 │
            │    │                    hook, cta (1-10)    │                 │
            │    │                         │              │                 │
            │    └──── feedback ◄──────────┴──────────────┘                 │
            │                                                               │
            └── STOP when: (1) all scores >= threshold    -> "passed"      ─┘
                           (2) max_iters                  -> "max_iters"
                           (3) score did not rise for `patience` rounds -> "no_improvement"
                 return: the BEST attempt (not the last one!)
```

## 2. How is it different from Reflection? (see 06-reflection)

| | Reflection | Evaluator-Optimizer |
|---|---|---|
| Who critiques | The same agent critiques itself | A separate evaluator (different prompt, ideally a different model) |
| Criteria | Open-ended "what can be improved?" | **Explicit rubric** + scores |
| Stop | Often a fixed number of rounds | Threshold / no-improvement / budget |

Evaluator-optimizer shines when there are **clear evaluation criteria** and iteration brings a measurable gain
(translation nuance, copywriting, code that must pass tests, SQL that must validate).

## 3. Types of evaluators

```
 cheapest ─────────────────────────────────────────────────────────► costliest
 ┌─────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌──────────────┐
 │ Code checks │   │ Execution / tool │   │ LLM-as-judge    │   │ Human review │
 │ length,     │   │ tests pass? SQL  │   │ rubric scores + │   │              │
 │ regex,      │   │ runs? link 200?  │   │ feedback        │   │              │
 │ schema      │   │                  │   │                 │   │              │
 └─────────────┘   └──────────────────┘   └─────────────────┘   └──────────────┘
   deterministic      ground truth           subjective quality     final authority
```
**Order matters**: run the cheap deterministic checks first. If they fail, don't spend money on the LLM judge
(`optimize()` does exactly this: hard fail -> evaluator skipped).

## 4. Stop criteria (all three are required)

1. **Passed**: every criterion `>= threshold`. (Not the total score but each criterion, so that a high score on one criterion cannot hide a very weak one.)
2. **max_iters**: a hard cap on cost/latency.
3. **No improvement (patience)**: LLMs sometimes make things worse while "improving" them (oscillation). That is why you return the **best** attempt, not the last.

## 5. When to use it / when not to

Use it when:
- There is a clear rubric and feedback genuinely makes the output better.
- The first draft is usually "almost there".

Don't use it when:
- The evaluator is unreliable (vague criteria) -> the loop becomes a random walk.
- Latency is critical (every iteration costs 2 calls).
- A good prompt already gets it right the first time.

## 6. Production pitfalls

- **Self-grading bias**: a model rates its own work too highly. Use a different model for the evaluator (`EVAL_MODEL`).
- **Lenient judge**: everything gets 9/10. Say "be strict, 8+ = genuinely great" in the prompt, add few-shot examples, and calibrate the judge.
- **Vague feedback**: "make it better" is useless. Ask the evaluator for *specific, actionable* feedback.
- **Missing criteria**: the judge didn't score a criterion at all -> treat it as 0 (`evaluate()` does this); never pass silently.
- **Oscillation**: track the best-so-far.
- **Counting with an LLM**: count characters/hashtags in code; LLMs miscount.

## 7. How this project uses it

| Concept | File / function |
|---|---|
| Generator with feedback | `evalopt_loop.py` -> `generate(llm, brief, previous)` |
| Hard deterministic checks | `hard_checks()` (length, hashtags) |
| LLM judge with rubric | `evaluate()` -> `llm_json(..., Evaluation)` + `RUBRIC` |
| Strict missing-criterion handling | `evaluate()` -> missing score = 0 |
| 3 stop criteria + best tracking | `optimize()` -> `stop_reason`, `best` |
| Separate models | `main.py` -> `GEN_MODEL`, `EVAL_MODEL` |
