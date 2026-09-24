# Orchestrator-Workers

## 1. Concept kya hai?

Ek **orchestrator** LLM goal dekh ke **runtime pe** decide karta hai ki kaunse subtasks chahiye, har subtask
ek **worker** (specialised LLM call) ko deta hai, aur end mein ek **synthesizer** sab outputs ko ek deliverable mein jodta hai.

```
                              PLAN (JSON, runtime pe bana)
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
        wave 2              ▼   (pricing ka output context mein)
                     [writer: hero]
                            │
                            ▼
                     SYNTHESIZER ──► final launch kit
```

## 2. Parallelization (03) se farak: yahi sabse important point

```
 PARALLELIZATION (sectioning)                ORCHESTRATOR-WORKERS
 ────────────────────────────                ─────────────────────
 subtasks CODE mein fixed:                   subtasks LLM runtime pe banata hai:
   ASPECTS = [security, perf, readability]     "launch kit" -> pricing, risks, hero
 har input pe same 3                          "migration plan" -> audit, schema, rollback, comms
 predictable, sasta                           flexible, lekin plan galat bhi ho sakta hai
```
Jab tum pehle se nahi bata sakte ki kitne aur kaunse subtasks honge (e.g. coding agent: "kaunsi files badlengi?
input pe depend karta hai"), tab orchestrator-workers.

## 3. Agent se farak?

Orchestrator **ek baar** plan banata hai, phir code us plan ko execute karta hai. Agent (ReAct) har step ke baad
dobara sochta hai. Isliye yeh "dynamic workflow" hai: workflow aur agent ke beech mein.
Plan-and-execute (05) isi ka agentic cousin hai jo zarurat pe **re-plan** bhi karta hai.

## 4. Subtypes / variants

| Variant | Kya | Is project mein |
|---|---|---|
| Flat workers | saare subtasks independent, ek wave | `depends_on` khaali ho to |
| DAG workers | subtasks ki dependencies, topological waves | `waves()` |
| Typed workers | har worker type ka apna prompt/model/tools | `WORKERS` dict |
| Workers as agents | har worker khud tools wala Agent | Tinker #3 |
| Hierarchical | worker khud orchestrator (sub-team) | 06-multi-agent-systems mein |
| Model split | strong orchestrator, cheap workers | `ORCH_MODEL` / `WORKER_MODEL` |

## 5. Guards (orchestrator pe andha bharosa mat karo)

LLM ka plan = untrusted input. Validate karo:
- **Cap**: max subtasks (`max_subtasks`), warna 40 subtasks = 40 calls ka bill.
- **Unknown worker type** -> `generalist` fallback.
- **Invalid dependencies**: non-existent id ya khud pe dependency -> hata do.
- **Cycles**: a needs b, b needs a -> `waves()` ValueError.
- **Worker failure isolated**: ek worker fail -> baaki chalte rahein, synthesizer ko `[FAILED]` bata do.
- **Parallelism cap**: `max_parallel` (rate limits).

## 6. Kab use karein / kab nahi

Use karo:
- Complex task jiske subtasks input pe depend karte hain (research reports, multi-file code changes, launch plans).
- Subtasks mein alag expertise chahiye.

Mat karo:
- Subtasks hamesha same hain -> sectioning (sasta, predictable).
- Task itna chhota ki ek call kaafi hai.
- Execution ke beech mein results dekh ke plan badalna padta hai -> plan-and-execute with re-planning / agent.

## 7. Production pitfalls

- **Over-decomposition**: orchestrator 2 ki jagah 8 subtasks bana deta hai. Prompt mein "SMALLEST set" + cap.
- **Context starvation**: worker ko sirf apna instruction milta hai; overall goal bhi pass karo (`run_worker` karta hai).
- **Synthesis drift**: synthesizer worker facts badal deta hai. Usko "combine, don't invent" bolo; zarurat ho to evaluator lagao.
- **Cost**: 1 plan + N workers + 1 synth. Cheap workers use karo.
- **Tracing**: plan aur har worker ka output log karo, warna "final report galat kyun hai" debug nahi hoga.

## 8. Is project mein kaise use ho raha hai

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
