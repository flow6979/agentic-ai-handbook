# Testing: orchestrator-workers (launch kit builder)

## Setup
Repo root: `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.
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

## Kya dekhna hai

```
=== PLAN (decided at runtime by the orchestrator) ===
wave 1: pricing<researcher>, risks<analyst>        <- parallel
wave 2: hero<writer>                               <- pricing ka output chahiye tha

=== WORKER OUTPUTS ===
[hero / writer] ok=True
Ship in 60 seconds ... cheaper than Render ...     <- pricing context use hua
```

- Real LLM pe **do alag goals** do (launch kit vs migration plan) aur dekho plan kitna alag banta hai: subtasks ki count aur worker types. Yahi "dynamic" hai.
- Dekho orchestrator `depends_on` sahi use kar raha hai ya sab independent bana deta hai.

## Offline tests

```bash
pytest 02-agentic-architectures/08-orchestrator-workers -v
```
- `test_end_to_end_plan_workers_synthesis`: plan -> 3 workers -> synthesizer ko sab outputs mile. (Writer ke fake mein assert hai ki pricing context mila.)
- `test_waves_respect_dependencies_and_detect_cycles`: DAG ordering + cycle detection.
- `test_plan_is_sanitised`: 10 subtasks -> 4 (cap), unknown worker -> generalist, ghost/self deps hate.
- `test_worker_failure_is_isolated`: ek worker crash, baaki chale, synth ko `[FAILED]` pata chala.

## Tinker karo

1. **Plan inspect karo**: 5 alag goals pe real LLM chalao, har plan print karo. Kya orchestrator over-decompose karta hai? `ORCH_SYSTEM` tweak karke fix karo.
2. **Naya worker type**: `WORKERS["legal"] = "..."` add karo aur goal do "launch in EU". Orchestrator use chunta hai?
3. **Workers as agents**: `run_worker` mein `llm.complete` ki jagah `agentkit.Agent(llm, tools=[...])` use karo (e.g. researcher ko web search tool, 03-web-agents se). Ab har worker khud tools chala sakta hai.
4. **Evaluator after synthesis**: 07 ka evaluator lagao final kit pe; fail ho to synthesizer ko feedback ke saath dobara chalao.
5. **Cost report**: har call ka `usage` jodo (orch vs workers alag). Cheap worker model se kitna bacha?
6. **Re-planning**: agar koi worker fail ho to orchestrator ko failures dikha ke naya plan maango. Ab yeh plan-and-execute (05) ban gaya: farak note karo.
