**Language:** [Hinglish](CONCEPTS.md) · English

# ReWOO: Reasoning WithOut Observation

## 1. The problem with ReAct

In ReAct the LLM is called again after every tool call, and each time the **whole history** (system
prompt + tool schemas + all previous steps) is sent again. 5 tool calls = 6 LLM calls,
and each call is bigger than the last.

```
ReAct:   LLM ─► tool ─► LLM ─► tool ─► LLM ─► tool ─► LLM ─► answer
         [ctx]         [ctx+1]        [ctx+2]        [ctx+3]      ← the context grows every time
```

In many tasks all the tool calls are known **up front**. "Get the heights of Everest and the Eiffel Tower,
then divide": there is no need to think in between.

## 2. The ReWOO idea

Paper: Xu et al., 2023. Three modules:

```
                    ┌──────────────────────────────────────┐
  Task ───────────► │ PLANNER (1 LLM call)                 │
                    │ Plan: Everest height                 │
                    │ #E1 = lookup[everest height]         │
                    │ Plan: Eiffel height                  │
                    │ #E2 = lookup[eiffel height]          │
                    │ Plan: divide                         │
                    │ #E3 = calculator[#E1 / #E2]          │  ← variables!
                    └──────────────────┬───────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │ WORKERS (no LLM*)                    │
                    │  #E1 → "8849"                        │
                    │  #E2 → "330"      (parallel!)        │
                    │  #E3 = calculator["8849 / 330"]      │  ← substitute
                    │      → "26.8152"                     │
                    └──────────────────┬───────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │ SOLVER (1 LLM call)                  │
                    │ plan + evidence → final answer       │
                    └──────────────────────────────────────┘
   * an LLM call happens only where an "LLM[...]" worker is used
```

**Result:** even for 5 tool calls, only 2 LLM calls (planner + solver). Far fewer tokens.

## 3. Variables (#E1, #E2) and the dependency graph

The plan is actually a **DAG** (dependency graph):

```
   #E1 (everest) ──┐
                   ├──► #E4 = #E1/#E2 ──► #E5 = #E4 * #E3
   #E2 (eiffel) ───┘                        ▲
   #E3 (japan) ─────────────────────────────┘

   level 0: [#E1, #E2, #E3]   ← they don't depend on each other → PARALLEL
   level 1: [#E4]
   level 2: [#E5]
```

`dependency_levels()` computes exactly these levels, and the workers of the same level run in parallel
in a `ThreadPoolExecutor`. (The LLMCompiler paper takes this idea further: streaming DAG execution.)

## 4. ReAct vs Plan-and-Execute vs ReWOO

| | ReAct | Plan-and-Execute | ReWOO |
|---|---|---|---|
| LLM calls | after every tool | plan + executor per step + replanner | **2** (planner + solver) |
| Adaptivity | very high | medium (replanner) | **low**: the plan is fixed |
| Tokens | high (history repeated) | medium | **low** |
| Latency | high | high | low (parallel workers) |
| Failure handling | the model reacts immediately | replan | the solver just gets ERROR evidence |
| Best for | exploratory tasks | long multi-step tasks | predictable, tool-heavy tasks |

**Trade-off:** ReWOO executes "blindly". If #E1 fails or returns something unexpected, the plan
doesn't change. Fix: replan on failure (hybrid), or fall back to ReAct.

## 5. Variants

- **ReWOO (this project):** sequential/level-parallel workers.
- **LLMCompiler:** the planner streams, and tasks start on a DAG scheduler as soon as their deps are ready; re-plan on failure (the "joiner").
- **Plan-then-verify:** validate the evidence before the solver.
- **Hybrid:** try ReWOO; if any evidence is an ERROR, fall back to ReAct/a replanner.

## 6. Production pitfalls

- **Keep plan parsing strict:** unknown tool, undefined variable reference → error immediately (`parse_plan`).
  Never execute the model's plan blindly.
- **Type issues with substitution:** if `#E1` outputs "8849 metres", the calculator fails. So keep tool
  outputs clean/predictable, or add an `LLM[extract number from #E1]` step in between.
- **Injection:** a tool output (a web page) gets substituted and becomes another tool's input. Validate it.
- **Thread safety:** parallel workers update shared counters → lock (`self._lock`).

## 7. How this project uses it

| Concept | File / function |
|---|---|
| Numeric-output workers | `rewoo_tools.py` (`lookup`, `calculator`) |
| Planner prompt (`Plan:` + `#En = tool[input]`) | `rewoo_agent.py` → `PLANNER_PROMPT` |
| Strict plan parsing + validation | `parse_plan()` |
| DAG levels / parallel execution | `dependency_levels()`, `ReWOO.run()` (ThreadPoolExecutor) |
| Variable substitution | `ReWOO._work()` (`_REF.sub`) |
| LLM as a worker | `LLM[...]` step in `_work()` |
| Solver | `SOLVER_PROMPT` |
| ReAct vs ReWOO token comparison | `main.py --compare` / `--offline` |
