# ReWOO: Reasoning WithOut Observation

## 1. ReAct ki problem

ReAct mein har tool call ke baad LLM dobara call hota hai, aur har baar **poori history** (system
prompt + tool schemas + saare pichle steps) dobara bheji jaati hai. 5 tool calls = 6 LLM calls,
aur har call pichle se bada.

```
ReAct:   LLM ─► tool ─► LLM ─► tool ─► LLM ─► tool ─► LLM ─► answer
         [ctx]         [ctx+1]        [ctx+2]        [ctx+3]      ← context har baar badhta hai
```

Bahut tasks mein saare tool calls **pehle se** pata hote hain. "Everest aur Eiffel ki height lao,
divide karo": iske liye beech mein sochne ki zaroorat hi nahi.

## 2. ReWOO ka idea

Paper: Xu et al., 2023. Teen modules:

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
                    │ WORKERS (koi LLM nahi*)              │
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
   * sirf "LLM[...]" worker use ho to wahan LLM call hota hai
```

**Result:** 5 tool calls ke liye bhi sirf 2 LLM calls (planner + solver). Tokens bahut kam.

## 3. Variables (#E1, #E2) aur dependency graph

Plan actually ek **DAG** (dependency graph) hai:

```
   #E1 (everest) ──┐
                   ├──► #E4 = #E1/#E2 ──► #E5 = #E4 * #E3
   #E2 (eiffel) ───┘                        ▲
   #E3 (japan) ─────────────────────────────┘

   level 0: [#E1, #E2, #E3]   ← ek doosre pe depend nahi → PARALLEL
   level 1: [#E4]
   level 2: [#E5]
```

`dependency_levels()` yahi levels nikaalta hai, aur same level ke workers `ThreadPoolExecutor`
mein parallel chalte hain. (LLMCompiler paper isi idea ko aage le jata hai: streaming DAG execution.)

## 4. ReAct vs Plan-and-Execute vs ReWOO

| | ReAct | Plan-and-Execute | ReWOO |
|---|---|---|---|
| LLM calls | har tool ke baad | plan + har step executor + replanner | **2** (planner + solver) |
| Adaptivity | bahut zyada | medium (replanner) | **kam**: plan fix hai |
| Tokens | zyada (history repeat) | medium | **kam** |
| Latency | high | high | low (parallel workers) |
| Failure handling | model turant react karta hai | replan | solver ko ERROR evidence milta hai, bas |
| Best for | exploratory tasks | lambe multi-step tasks | predictable, tool-heavy tasks |

**Trade-off:** ReWOO "andha" execute karta hai. Agar #E1 fail hua ya unexpected result aaya, plan
nahi badalta. Fix: failure pe replan (hybrid), ya ReAct pe fallback.

## 5. Variants

- **ReWOO (yeh project):** sequential/level-parallel workers.
- **LLMCompiler:** planner stream karta hai, tasks DAG scheduler pe jaise hi deps ready ho chalne lagte hain; failure pe re-plan ("joiner").
- **Plan-then-verify:** solver se pehle evidence validate karo.
- **Hybrid:** ReWOO try karo; koi evidence ERROR ho to ReAct/replanner pe gir jao.

## 6. Production pitfalls

- **Plan parsing strict rakho:** unknown tool, undefined variable reference → turant error (`parse_plan`).
  Model ke plan ko blindly execute mat karo.
- **Substitution ke type issues:** `#E1` ka output "8849 metres" ho to calculator fail. Isliye tools ka
  output clean/predictable rakho, ya beech mein `LLM[extract number from #E1]` step lo.
- **Injection:** tool output (web page) substitute hoke doosre tool ka input ban jaata hai. Validate karo.
- **Thread safety:** parallel workers shared counters update karte hain → lock (`self._lock`).

## 7. Is project mein kaise use ho raha hai

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
