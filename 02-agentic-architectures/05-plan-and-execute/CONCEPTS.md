# Plan-and-Execute

## 1. Idea

ReAct har step pe sochta hai: "ab kya karun?" Chhote tasks ke liye yeh badhiya hai, lekin lambe
tasks mein model **big picture bhool jata hai** (context bhar jata hai, ek hi cheez baar baar
karta hai, ya beech mein bhatak jata hai).

**Plan-and-Execute** kaam ko do roles mein baant deta hai:

- **Planner:** pehle poora plan banao (steps ki list). Yeh "architect" hai.
- **Executor:** ek time pe sirf ek step karo, tools ke saath. Yeh "mistri" hai.
- **Replanner:** har step ke baad dekho: plan sahi chal raha hai? badalna hai? kaam ho gaya?

```
                 ┌──────────────┐
   Goal ───────► │   PLANNER    │  llm_json → Plan{steps:[...]}
                 └──────┬───────┘
                        │ [s1, s2, s3]
                        ▼
              ┌───────────────────┐
     ┌──────► │ EXECUTOR (1 step) │  chhota ReAct agent + tools
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

## 2. Kyun kaam karta hai?

1. **Separation of concerns:** planner ko tool details ki fikar nahi, executor ko poore goal
   ki nahi. Dono ke prompts chhote aur focused hote hain.
2. **Chhota executor context:** executor ko sirf current step + pichle results ka summary
   milta hai, poora chat history nahi. Tokens kam, focus zyada.
3. **Model mix kar sakte ho:** planner ke liye bada/smart model (e.g. `anthropic:claude-sonnet-5`),
   executor ke liye sasta/fast model (e.g. `groq:llama-3.1-8b-instant`). Cost bachta hai.
4. **Plan dikhta hai:** user ko plan dikha ke approval le sakte ho (human-in-the-loop, dekho `11`).

## 3. Replanning: yeh part sabse important hai

Plan pehle se bana hai, lekin duniya plan ke hisaab se nahi chalti. Tool fail hote hain, results
surprise dete hain. Replanner ke teen decisions:

| Decision | Kab | Is project mein |
|---|---|---|
| `continue` | Step theek hua, baaki plan valid hai | Weather mila, aage badho |
| `replan` | Step fail hua ya naya info plan badalta hai | Kasol ki flight nahi hai, Jaipur ka plan banao |
| `finish` | Goal pura ho gaya (plan ke steps bache ho tab bhi) | Total cost mil gaya |

Guardrails: `max_replans` (warna model replan-loop mein phas sakta hai) aur `max_steps`.

## 4. Variants / subtypes

- **Plan-and-Solve (prompting only):** ek hi LLM call mein "pehle plan likho, phir solve karo".
  Koi tools/loop nahi. Sabse sasta.
- **Plan-and-Execute (yeh project):** alag planner + executor + replanner loop.
- **Static plan (no replanner):** plan ek baar, execute blindly. Fast, lekin fail hone pe atak jata hai.
- **ReWOO:** plan mein hi tool calls + variables (#E1) likho, beech mein koi LLM call nahi. Dekho `09-rewoo`.
- **LLMCompiler:** plan ko DAG banao aur independent steps **parallel** chalao.
- **Hierarchical planning:** high-level plan → har step ka sub-plan (multi-agent systems mein aam).

## 5. Kab use karein / kab nahi

**Use karo:** multi-step tasks jinke steps pehle se kuch had tak pata hain (trip planning,
report banana, data pipeline, migrations), aur jab tumhe plan user ko dikhana ho.

**Mat use karo:** 1-2 step tasks (overhead zyada, ReAct kaafi hai), ya highly exploratory tasks
jahan har result next step poori tarah badal deta hai (wahan ReAct better hai).

**Trade-off:** replanner har step ke baad ek extra LLM call hai. Sasta karna ho to sirf failure pe
replan karo (tinker exercise dekho).

## 6. Production pitfalls

- **Over-planning:** planner 15 steps bana deta hai. Prompt mein limit do ("2-6 steps").
- **Vague steps:** "research the topic". Planner ko tools ki list do taaki steps actionable ho.
- **Failure detection:** yahan convention hai `FAILED:` prefix. Production mein structured
  output (`{status, result}`) use karo, string matching fragile hai.
- **State passing:** executor ko pichle results chahiye. Hum summary list bhejte hain; bade results
  ke liye unhe store karke sirf reference/summary bhejo.

## 7. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Fake trip tools (ek tool jaanboojh ke fail hota hai) | `planexec_tools.py` |
| Plan schema (structured output) | `planexec_agent.py` → `Plan`, `Step` |
| Planner | `PlanAndExecute.plan()` → `llm_json(..., Plan)` |
| Executor = chhota ReAct agent per step | `PlanAndExecute.execute_step()` (agentkit `Agent`, `max_steps=4`) |
| Failure detection | `StepRecord.failed` (`FAILED:` prefix) |
| Replanner decision | `ReplanDecision` + `PlanAndExecute.replan()` |
| Budgets | `max_steps`, `max_replans` in `PlanAndExecute.run()` |
| Plan versions (debugging) | `PlanExecResult.plans` (main.py v0, v1 print karta hai) |
