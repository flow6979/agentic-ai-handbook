**Language:** [Hinglish](CONCEPTS.md) · English

# Plan-and-Execute

## 1. Idea

ReAct thinks at every step: "what do I do now?" That is great for small tasks, but in long
tasks the model **loses the big picture** (the context fills up, it repeats the same thing,
or it drifts off course halfway).

**Plan-and-Execute** splits the work into two roles:

- **Planner:** first make the whole plan (a list of steps). This is the "architect".
- **Executor:** do only one step at a time, with tools. This is the "builder".
- **Replanner:** after every step, check: is the plan on track? does it need to change? is the work done?

```
                 ┌──────────────┐
   Goal ───────► │   PLANNER    │  llm_json → Plan{steps:[...]}
                 └──────┬───────┘
                        │ [s1, s2, s3]
                        ▼
              ┌───────────────────┐
     ┌──────► │ EXECUTOR (1 step) │  small ReAct agent + tools
     │        └─────────┬─────────┘
     │                  │ StepRecord(result, failed?)
     │                  ▼
     │        ┌───────────────────┐
     │        │    REPLANNER      │  llm_json → ReplanDecision
     │        └──┬──────┬──────┬──┘
     │  continue │      │replan│ finish
     └───────────┘      │      └────────► Final answer
     ▲                  ▼
     └──── remaining = new_steps
```

## 2. Why does it work?

1. **Separation of concerns:** the planner doesn't worry about tool details, the executor doesn't worry about the whole
   goal. Both prompts are small and focused.
2. **Small executor context:** the executor only gets the current step + a summary of previous results,
   not the whole chat history. Fewer tokens, more focus.
3. **You can mix models:** a big/smart model for the planner (e.g. `anthropic:claude-sonnet-5`),
   a cheap/fast model for the executor (e.g. `groq:llama-3.1-8b-instant`). This saves cost.
4. **The plan is visible:** you can show the plan to the user and get approval (human-in-the-loop, see `11`).

## 3. Replanning: this is the most important part

The plan is made upfront, but the world doesn't follow the plan. Tools fail, results
surprise you. The replanner's three decisions:

| Decision | When | In this project |
|---|---|---|
| `continue` | The step went fine, the rest of the plan is valid | Got the weather, move on |
| `replan` | The step failed or new info changes the plan | No flight to Kasol, make a plan for Jaipur |
| `finish` | The goal is done (even if plan steps remain) | Got the total cost |

Guardrails: `max_replans` (otherwise the model can get stuck in a replan loop) and `max_steps`.

## 4. Variants / subtypes

- **Plan-and-Solve (prompting only):** in a single LLM call, "first write a plan, then solve it".
  No tools/loop. The cheapest.
- **Plan-and-Execute (this project):** separate planner + executor + replanner loop.
- **Static plan (no replanner):** plan once, execute blindly. Fast, but gets stuck when something fails.
- **ReWOO:** write the tool calls + variables (#E1) into the plan itself, no LLM calls in between. See `09-rewoo`.
- **LLMCompiler:** turn the plan into a DAG and run independent steps **in parallel**.
- **Hierarchical planning:** high-level plan → a sub-plan for each step (common in multi-agent systems).

## 5. When to use it / when not

**Use it:** multi-step tasks whose steps are known to some extent in advance (trip planning,
building a report, data pipelines, migrations), and when you want to show the plan to the user.

**Don't use it:** 1-2 step tasks (too much overhead, ReAct is enough), or highly exploratory tasks
where each result completely changes the next step (ReAct is better there).

**Trade-off:** the replanner is one extra LLM call after every step. To make it cheaper, replan only on
failure (see the tinker exercise).

## 6. Production pitfalls

- **Over-planning:** the planner produces 15 steps. Give a limit in the prompt ("2-6 steps").
- **Vague steps:** "research the topic". Give the planner the list of tools so the steps are actionable.
- **Failure detection:** the convention here is a `FAILED:` prefix. In production use structured
  output (`{status, result}`); string matching is fragile.
- **State passing:** the executor needs previous results. We send a summary list; for big results,
  store them and send only a reference/summary.

## 7. How this project uses it

| Concept | File / function |
|---|---|
| Fake trip tools (one tool fails on purpose) | `planexec_tools.py` |
| Plan schema (structured output) | `planexec_agent.py` → `Plan`, `Step` |
| Planner | `PlanAndExecute.plan()` → `llm_json(..., Plan)` |
| Executor = a small ReAct agent per step | `PlanAndExecute.execute_step()` (agentkit `Agent`, `max_steps=4`) |
| Failure detection | `StepRecord.failed` (`FAILED:` prefix) |
| Replanner decision | `ReplanDecision` + `PlanAndExecute.replan()` |
| Budgets | `max_steps`, `max_replans` in `PlanAndExecute.run()` |
| Plan versions (debugging) | `PlanExecResult.plans` (main.py prints v0, v1) |
