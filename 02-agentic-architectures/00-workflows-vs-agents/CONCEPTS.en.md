**Language:** [Hinglish](CONCEPTS.md) · English

# Workflows vs Agents: the full spectrum

> The very first question to ask when building any AI system:
> **"Who decides the steps: my code, or the LLM?"**

## 1. Three building blocks (Anthropic's "Building effective agents" taxonomy)

```
  less autonomy, more control                               more autonomy, less control
  ◄──────────────────────────────────────────────────────────────────────────────────►

  ┌─────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
  │ AUGMENTED LLM   │     │ WORKFLOWS                │     │ AUTONOMOUS AGENTS        │
  │                 │     │                          │     │                          │
  │ LLM + tools +   │     │ run LLM calls along a    │     │ the LLM decides in a     │
  │ retrieval +     │     │ path predefined in       │     │ loop: which tool, when,  │
  │ memory          │     │ CODE                     │     │ how many times, when     │
  │                 │     │                          │     │ to stop                  │
  │ (one call)      │     │ chaining, routing,       │     │                          │
  │                 │     │ parallel, orch-workers,  │     │ ReAct, plan-execute,     │
  │                 │     │ evaluator-optimizer      │     │ multi-agent...           │
  └─────────────────┘     └──────────────────────────┘     └──────────────────────────┘
        building block          code = control flow             LLM = control flow
```

- **Augmented LLM**: a single LLM call, but with tools/retrieval/memory. This is the "brick" everything else is built from.
- **Workflow**: you (the developer) write the flowchart in advance. The LLM does the work inside each box, but
  **code** decides which box runs when.
- **Agent**: there is no flowchart. The LLM gets a goal + tools, and decides by itself in a loop.

## 2. Same task, two ways (this folder's demo)

Task: "tell the user their cart total (with 18% tax) and write a friendly message"

```
WORKFLOW (spectrum_demo.run_as_chain)            AGENT (spectrum_demo.run_as_agent)
────────────────────────────────────             ──────────────────────────────────
 code: get_cart("u1")                             LLM: "first I need the cart"
   │                                                │  tool_call get_cart(u1)
   ▼                                                ▼
 code: subtotal = sum(...)                        LLM: "now compute the total"
   │                                                │  tool_call compute_total(4097)
   ▼                                                ▼
 code: compute_total(subtotal)                    LLM: final friendly message
   │
   ▼
 LLM: only writes the message  ← 1 LLM call       ← 3 LLM calls
```

| | Workflow | Agent |
|---|---|---|
| Who decides the steps | Code | LLM |
| Predictability | High (same input -> same path) | Low (the path can change) |
| Cost / latency | Low (fixed calls) | High (loop, full history on every step) |
| New/unexpected questions | Can't handle them | Handles them ("my 2nd cart?") |
| Testing | Easy (unit test each step) | Hard (needs evals) |
| Failure mode | Rigid on unexpected input | Loops, wrong tool, hallucinated args |

## 3. Decision guide: which architecture should you pick?

```
                    Can one LLM call (+ a good prompt / RAG) do the job?
                                 │
                   ┌──── yes ────┴──── no ──────┐
                   ▼                            ▼
           AUGMENTED LLM             Are the steps known in advance?
           (stop right here!)                   │
                                ┌──── yes ──────┴────── no ──────┐
                                ▼                                ▼
                  Are the steps sequential?           Do subtasks depend on the
                        │                             input, but is planning
             ┌── yes ───┴── no ───┐                   once enough?
             ▼                     ▼                         │
      PROMPT CHAINING     Different handling      ┌── yes ───┴── no ───┐
       (01)               per input type?         ▼                      ▼
                          │                ORCHESTRATOR-          Open-ended, unknown
                ┌─ yes ───┴── no ───┐       WORKERS (08)          number of steps,
                ▼                   ▼                              need feedback from
            ROUTING (02)     Independent parts /                  the environment?
                             need confidence?                            │
                                    │                                    ▼
                                    ▼                              AGENT (ReAct 04,
                            PARALLELIZATION (03)                   plan-execute 05...)

   Need to improve quality iteratively, with a clear rubric?  ──►  EVALUATOR-OPTIMIZER (07)
   (this combines with any of the above)
```

**Golden rule:** start with the simplest thing. Bring in an agent only when a workflow genuinely falls short.
Complexity means: more cost, more latency, more debugging.

## 4. Patterns at a glance (this section's folders)

| Folder | Pattern | Type | One line |
|---|---|---|---|
| 01 | Prompt chaining | Workflow | Sequential steps + code gates |
| 02 | Routing | Workflow | Classify -> specialised handler/model |
| 03 | Parallelization | Workflow | Sectioning (split) + Voting (repeat) |
| 07 | Evaluator-optimizer | Workflow | Generate -> judge -> feedback loop |
| 08 | Orchestrator-workers | Workflow (dynamic) | The LLM creates subtasks at runtime |
| 04+ | ReAct, plan-execute, reflection, ... | Agent | The LLM controls the loop |

Orchestrator-workers sits on the "border": the LLM makes the plan (like an agent), but execution
happens inside a fixed code structure (like a workflow).

## 5. Production pitfalls

- **An agent when a workflow was enough**: 5x the cost, and every run is different. Try a workflow first.
- **Making the LLM do math/lookups**: `compute_total` lives in code, not in the LLM. Only ask the LLM to do what only an LLM can do.
- **An agent without guards**: max_steps, tool errors sent back to the model, human approval (built into agentkit's `Agent`).
- **Reaching for frameworks too early**: LangGraph/CrewAI are good, but understand the raw pattern first (that is the whole point of this repo).

## 6. How this project uses it

| Concept | Where |
|---|---|
| Shared tools (both approaches use the same tools) | `spectrum_demo.py` -> `get_cart`, `compute_total` (`@tool`) |
| Workflow: code calls tools directly | `run_as_chain()` -> `get_cart.fn(...)`, `compute_total.fn(...)`, then one `llm.complete` |
| Agent: the LLM decides | `run_as_agent()` -> `agentkit.Agent` loop with tools |
| Cost comparison | `main.py` prints the "LLM calls" for both (1 vs 3) |
| Error recovery (agent) | `test_agent_recovers_from_bad_user_id` -> the tool error goes back to the model |
