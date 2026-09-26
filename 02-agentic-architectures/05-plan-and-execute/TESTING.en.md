**Language:** [Hinglish](TESTING.md) · English

# 05-plan-and-execute: Testing and tinkering

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + key in `.env`.

## 1. Offline demo

```bash
python 02-agentic-architectures/05-plan-and-execute/main.py --offline
```

In the output, look for:
- `=== Plans ===` → `v0` (the Kasol one) and `v1` (the Jaipur one). Proof of replanning.
- `✗ Find flights from Delhi to Kasol` → the tool raised `LookupError`, the executor said `FAILED:`.
- The `REPLANNER: replan (...)` line in the trace (stderr).

## 2. Real LLM

```bash
python 02-agentic-architectures/05-plan-and-execute/main.py "Plan a 2-night trip from Delhi to Goa. Check weather, cheapest flight, a hotel, and total cost."
python 02-agentic-architectures/05-plan-and-execute/main.py "Weekend trip from Delhi to Manali with total cost"
```

In the second one, `search_flights(Delhi, Manali)` will fail (there is no data). Watch how the real model
replans: does it change the city without asking the user? Is that right?

What to check:
- How many steps did the planner create? Do they match the tools?
- Is the executor doing only one thing per step, or running ahead?
- Does the replanner say `finish` at the right time?

## 3. Offline tests

```bash
pytest 02-agentic-architectures/05-plan-and-execute -v
```

Covers: tools (safe calculator), happy path (continue → finish), failure → replan, replan budget (an infinite replan loop gets stopped).

## 4. Tinker with it

1. **Model mixing:** use separate `planner_llm` and `executor_llm` in `PlanAndExecute`. Use
   `get_llm("anthropic:...")` for the planner and `get_llm("groq:llama-3.1-8b-instant")` for the executor. Compare quality and cost.
2. **Replan only on failure:** in `run()`, call the replanner only when `rec.failed` or when the steps run out.
   How many LLM calls did you save? Did quality drop?
3. **Structured step result:** instead of the `FAILED:` string, get
   `{status: "ok"|"failed", result: str}` from the executor via `llm_json`.
4. **Human approval of the plan:** after `plan()`, print the plan and confirm with `input("approve? ")`.
   On rejection, make a new plan with the user's feedback.
5. **Parallel steps (the LLMCompiler idea):** also get `depends_on: list[int]` from the planner and run independent steps
   in parallel in a `concurrent.futures.ThreadPoolExecutor`.
