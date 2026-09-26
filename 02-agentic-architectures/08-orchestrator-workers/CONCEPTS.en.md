**Language:** [Hinglish](CONCEPTS.md) · English

# Orchestrator-Workers

## 1. What is the concept?

An **orchestrator** LLM looks at the goal and decides **at runtime** which subtasks are needed, hands each subtask
to a **worker** (a specialised LLM call), and at the end a **synthesizer** combines all the outputs into one deliverable.

```
                              PLAN (JSON, built at runtime)
                         ┌──────────────────────────────────┐
  goal ──► ORCHESTRATOR ─┤ pricing  -> researcher            │
           (strong LLM)  │ risks    -> analyst               │
                         │ hero     -> writer (needs pricing)│
                         └──────────────────────────────────┘
                                         │
                       waves() = dependency order
                                         │
        wave 1 (parallel)   ┌────────────┴────────────┐
                            ▼                         ▼
                     [researcher: pricing]     [analyst: risks]
                            │
        wave 2              ▼   (pricing output goes into the context)
                     [writer: hero]
                            │
                            ▼
                     SYNTHESIZER ──► final launch kit
```

## 2. How it differs from Parallelization (03): the most important point

```
 PARALLELIZATION (sectioning)                ORCHESTRATOR-WORKERS
 ────────────────────────────                ─────────────────────
 subtasks fixed in CODE:                     subtasks created by the LLM at runtime:
   ASPECTS = [security, perf, readability]     "launch kit" -> pricing, risks, hero
 same 3 for every input                       "migration plan" -> audit, schema, rollback, comms
 predictable, cheap                           flexible, but the plan can also be wrong
```
Use orchestrator-workers when you cannot tell in advance how many subtasks there will be or which ones (e.g. a coding
agent: "which files will change? It depends on the input").

## 3. How is it different from an agent?

The orchestrator makes the plan **once**, then code executes that plan. An agent (ReAct) thinks again after
every step. That's why this is a "dynamic workflow": somewhere between a workflow and an agent.
Plan-and-execute (05) is its agentic cousin that also **re-plans** when needed.

## 4. Subtypes / variants

| Variant | What | In this project |
|---|---|---|
| Flat workers | all subtasks independent, one wave | when `depends_on` is empty |
| DAG workers | subtasks have dependencies, topological waves | `waves()` |
| Typed workers | each worker type has its own prompt/model/tools | `WORKERS` dict |
| Workers as agents | each worker is itself an Agent with tools | Tinker #3 |
| Hierarchical | a worker is itself an orchestrator (sub-team) | in 06-multi-agent-systems |
| Model split | strong orchestrator, cheap workers | `ORCH_MODEL` / `WORKER_MODEL` |

## 5. Guards (don't blindly trust the orchestrator)

The LLM's plan = untrusted input. Validate it:
- **Cap**: max subtasks (`max_subtasks`), otherwise 40 subtasks = a bill for 40 calls.
- **Unknown worker type** -> fall back to `generalist`.
- **Invalid dependencies**: a non-existent id or a self-dependency -> remove it.
- **Cycles**: a needs b, b needs a -> `waves()` raises ValueError.
- **Worker failure isolated**: one worker fails -> the rest keep running, and the synthesizer is told `[FAILED]`.
- **Parallelism cap**: `max_parallel` (rate limits).

## 6. When to use it / when not to

Use it when:
- The task is complex and its subtasks depend on the input (research reports, multi-file code changes, launch plans).
- Subtasks need different expertise.

Don't use it when:
- The subtasks are always the same -> sectioning (cheap, predictable).
- The task is so small that one call is enough.
- You need to change the plan based on results mid-execution -> plan-and-execute with re-planning / an agent.

## 7. Production pitfalls

- **Over-decomposition**: the orchestrator creates 8 subtasks instead of 2. Put "SMALLEST set" in the prompt + a cap.
- **Context starvation**: a worker only gets its own instruction; pass the overall goal too (`run_worker` does this).
- **Synthesis drift**: the synthesizer changes the workers' facts. Tell it to "combine, don't invent"; add an evaluator if needed.
- **Cost**: 1 plan + N workers + 1 synth. Use cheap workers.
- **Tracing**: log the plan and each worker's output, otherwise you can't debug "why is the final report wrong".

## 8. How this project uses it

| Concept | File / function |
|---|---|
| Runtime planning (structured) | `orchestrator_workers.py` -> `make_plan()` -> `llm_json(..., Plan)` |
| Plan sanitisation (cap, unknown worker, bad deps) | `make_plan()` |
| DAG execution in waves | `waves()` + `orchestrate()` (ThreadPoolExecutor per wave) |
| Dependency context passing | `run_worker()` -> `[<id> output]` blocks |
| Typed workers | `WORKERS` dict (system prompt per type) |
| Failure isolation | `run_worker()` returns `ok=False`; `synthesize()` marks `[FAILED]` |
| Synthesis | `synthesize()` |
| Strong planner, cheap workers | `main.py` -> `ORCH_MODEL`, `WORKER_MODEL` |
