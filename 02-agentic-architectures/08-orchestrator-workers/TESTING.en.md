**Language:** [Hinglish](TESTING.md) · English

# Testing: orchestrator-workers (launch kit builder)

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + a key in `.env`.
Optional:
```
ORCH_MODEL=groq:llama-3.3-70b-versatile     # planning + synthesis (strong)
WORKER_MODEL=groq:llama-3.1-8b-instant      # workers (cheap)
```

## Run

```bash
python 02-agentic-architectures/08-orchestrator-workers/main.py --offline
python 02-agentic-architectures/08-orchestrator-workers/main.py
python 02-agentic-architectures/08-orchestrator-workers/main.py "Plan migrating a Rails monolith's auth to a separate service"
```

## What to look for

```
=== PLAN (decided at runtime by the orchestrator) ===
wave 1: pricing<researcher>, risks<analyst>        <- parallel
wave 2: hero<writer>                               <- needed the pricing output

=== WORKER OUTPUTS ===
[hero / writer] ok=True
Ship in 60 seconds ... cheaper than Render ...     <- the pricing context was used
```

- With a real LLM, give it **two different goals** (launch kit vs migration plan) and see how different the plans are: the number of subtasks and the worker types. That is what "dynamic" means.
- Check whether the orchestrator uses `depends_on` correctly or makes everything independent.

## Offline tests

```bash
pytest 02-agentic-architectures/08-orchestrator-workers -v
```
- `test_end_to_end_plan_workers_synthesis`: plan -> 3 workers -> the synthesizer received all outputs. (The writer's fake asserts that it got the pricing context.)
- `test_waves_respect_dependencies_and_detect_cycles`: DAG ordering + cycle detection.
- `test_plan_is_sanitised`: 10 subtasks -> 4 (cap), unknown worker -> generalist, ghost/self deps removed.
- `test_worker_failure_is_isolated`: one worker crashes, the rest run, and the synth learns about `[FAILED]`.

## Tinker with it

1. **Inspect the plan**: run the real LLM on 5 different goals and print every plan. Does the orchestrator over-decompose? Tweak `ORCH_SYSTEM` to fix it.
2. **New worker type**: add `WORKERS["legal"] = "..."` and give the goal "launch in EU". Does the orchestrator pick it?
3. **Workers as agents**: in `run_worker`, use `agentkit.Agent(llm, tools=[...])` instead of `llm.complete` (e.g. give the researcher a web search tool from 03-web-agents). Now each worker can run tools itself.
4. **Evaluator after synthesis**: put the evaluator from 07 on the final kit; if it fails, re-run the synthesizer with the feedback.
5. **Cost report**: add up the `usage` of every call (orch vs workers separately). How much did the cheap worker model save?
6. **Re-planning**: if a worker fails, show the failures to the orchestrator and ask for a new plan. Now it has become plan-and-execute (05): note the difference.
