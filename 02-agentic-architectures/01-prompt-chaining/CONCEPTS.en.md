**Language:** [Hinglish](CONCEPTS.md) · English

# Prompt Chaining

## 1. What is the concept?

Instead of stuffing a big, hard task into one giant prompt, break it into **small sequential steps**.
Each step is one focused LLM call, and its output becomes the next step's input.
Between steps sit **gates**: plain code checks that make sure the output is fine.

```
            ┌──────────┐     ┌──────┐     ┌──────────┐     ┌──────┐     ┌──────────┐
  topic ───►│ OUTLINE  │────►│ GATE │────►│  DRAFT   │────►│ GATE │────►│  POLISH  │───► blog post
            │ (LLM,    │     │(code)│     │ (LLM)    │     │(code)│     │  (LLM)   │
            │  JSON)   │     └──┬───┘     └──────────┘     └──┬───┘     └──────────┘
            └──────────┘        │ fail                        │ fail
                 ▲              │ + feedback                  │ + feedback
                 └──────────────┘            ▲────────────────┘
                     retry (max N)          retry (max N)        still failing after N -> STOP (GateError)
```

### Why does it work?
- Each LLM call has a **small, clear** job -> accuracy goes up (the model thinks about one thing at a time).
- Intermediate outputs are **visible** -> debugging is easy (which step broke?).
- Gates **stop bad output from travelling further** (no garbage in -> garbage out).
- You can use a different model/temperature for each step.

Trade-off: more LLM calls = more **latency** (steps are sequential) and slightly more cost.

## 2. Gates: the heart of chaining

Gate = a deterministic Python check. **Don't ask the LLM to check what code can check.**

| Gate type | Example | In this project |
|---|---|---|
| Schema / format | Is the JSON valid? Are the fields there? | `llm_json` + Pydantic `Outline` |
| Count / length | 3-5 sections, min 40 words | `check_outline`, `check_draft` |
| Consistency | Does the draft contain every outline heading? | `check_draft` |
| Uniqueness | no duplicate headings | `check_outline` |
| (optional) LLM gate | "is this on-topic?" | not here; add it when needed |

When a gate fails, there are 3 options:
```
 gate fail ──┬──► retry same step, error message as feedback   (here: run_step_with_gate)
             ├──► fallback (default value / simpler path)
             └──► stop pipeline, raise error                   (after N attempts)
```

## 3. Subtypes / variants

1. **Linear chain**: A -> B -> C (this project).
2. **Chain with gates + retry**: validate after each step, retry with feedback on failure (this project).
3. **Map-reduce chain**: one step produces a list, the same step runs on each item (map), then combine (reduce).
   Here you can turn `step_draft` into map-reduce by calling it per section (Tinker #2).
4. **Conditional chain**: branch on a step's output (this leads towards routing, see 02).
5. **Multi-model chain**: a cheap model for the outline, a strong model for the draft.

## 4. When to use it / when not

Use it when:
- The task breaks into natural steps (outline -> draft -> edit, extract -> transform -> summarise).
- Each step's output can be checked.
- Accuracy matters more than latency.

Don't use it when:
- A single prompt already gives a good result (extra calls = waste).
- The steps are not known in advance (then you need an agent / orchestrator).
- You need real-time, low latency (e.g. chat autocomplete).

## 5. Production pitfalls

- **Error compounding**: a small mistake in step 1 grows big by step 3 -> hence gates.
- **Context loss**: each step only gets the previous step's output. Pass important info (tone, audience) explicitly.
- **Infinite retry**: always cap retries (`max_attempts`).
- **An LLM inside the gate**: an LLM-based gate can also be wrong; deterministic checks first.
- **Observability**: log every step's input/output (`ChainResult.log`), otherwise you won't know which step failed.

## 6. How this project uses it

| Concept | File / function |
|---|---|
| Structured step output | `step_outline()` -> `llm_json(..., Outline)` |
| Free-text steps | `step_draft()`, `step_polish()` -> `llm.complete` |
| Gates | `check_outline()`, `check_draft()` raise `GateError` |
| Retry with feedback | `run_step_with_gate()`: the gate's error message goes into the next prompt as "previous ... was rejected: ..." |
| Stop on repeated failure | `run_step_with_gate()` raises `GateError` after N attempts |
| Step log / traceability | `ChainResult.log` |
| Offline demo (shows gate fail -> retry) | `offline_demo_llm()`: the first outline has duplicate headings |
