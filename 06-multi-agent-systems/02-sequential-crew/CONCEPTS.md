# 02 · Sequential Crew — Assembly line of agents

## Seedhi baat

Socho ek software team hai: PM requirements likhta hai, Architect design banata hai, Developer code likhta hai, aur QA check karta hai. Har insaan ka output agle ka input banta hai. **Sequential crew** bilkul yahi hai: fixed order mein agents, ek ke baad ek. CrewAI ka `Process.sequential` isi idea pe bana hai. Yahan hum usse from scratch bana rahe hain.

```
 idea
  │
  ▼
┌──────────┐ stories ┌───────────┐ design ┌───────────┐  files  ┌──────────┐
│    PM    │───────► │ Architect │──────► │ Developer │───────► │    QA    │
└──────────┘         └───────────┘        └───────────┘         └────┬─────┘
                                                ▲                    │
                                                │   passed=false     │
                                                └──── issues ────────┘
                                                  (max_reworks tak)
                                                     passed=true ──► DONE
```

## 3 building blocks

| Block | Kya hai | Code |
|---|---|---|
| **Role** | Kaun (title, goal, backstory, tools) | `Role` dataclass |
| **Task** | Kya karna hai: `description`, `expected_output`, kaunsa `role`, kin tasks ka `context` chahiye | `Task` dataclass |
| **Crew** | Tasks ko order mein chalata hai, outputs store karta hai | `SoftwareCrew.kickoff()` |

### Task ≠ Role (important!)

Role = **kaun**, Task = **kya**. Ek role kai tasks kar sakta hai (Developer: "implement" aur "fix"). Isliye inhe alag rakha hai.

### `expected_output` = contract

Har task batata hai ki output kis shape mein chahiye ("3-5 user stories with acceptance criteria"). Agla role isi shape pe depend karta hai. Yeh contract nahi hoga to Architect ko pata nahi chalega ki PM ke output mein kya dhundhe.

## Context passing (sabse important concept)

```
outputs = {}                         # shared "memory" of the crew
stories  ← PM(task)                  outputs["stories"]
design   ← Architect(task + stories) outputs["design"]
code     ← Dev(task + stories + design)
```

`Task.context=["stories", "design"]` explicitly batata hai ki kaunse pichhle outputs chahiye. **Sab kuch sabko mat bhejo**:

- ❌ **Context bleeding**: Developer ko PM ki poori soch aur Architect ki rough notes sab mil gayi, to prompt lamba ho gaya, focus gaya, aur cost badh gayi.
- ✅ Sirf declared dependencies bhejo. Test `test_context_passing_only_declared_dependencies` isi ko check karta hai.

## Tools per role

Sirf Developer ke paas `save_file` tool hai (`Workspace.as_tool()`). PM/QA ko file likhne ki zaroorat nahi, isliye unhe tool nahi diya. Yahi **least privilege** hai.

## Feedback loop (sequential + ek loop)

Pure sequential mein galti aage badhti jaati hai. Isliye QA ke baad ek **bounded rework loop** hai:
- QA structured verdict deta hai: `QAVerdict(passed, issues)`
- fail → Developer ko issues ke saath "fix" task, max `max_reworks` baar
- Budget khatam? Rook do aur `passed=false` report karo (**honest failure**, infinite loop nahi)

## Subtypes / variations

| Variation | Kya | Kab |
|---|---|---|
| **Pure sequential** | A→B→C, koi loop nahi | Simple content pipelines |
| **Sequential + review loop** (yeh project) | End mein reviewer, bounded rework | Quality chahiye |
| **Hierarchical process** | Manager decide kare kaun sa task kisko | Order pehle se fixed nahi (project 04) |
| **Parallel stages** | Independent tasks saath mein | Latency kam karni ho (section 02 parallelization) |
| **Human checkpoint** | Kisi stage ke baad human approve kare | High-stakes output |

## Trade-offs

- ✅ Predictable, debug karna aasaan, har stage ka output inspect kar sakte ho
- ✅ Har role ka prompt chhota aur focused rehta hai
- ❌ Latency = sab stages ka sum
- ❌ Shuruaat ki galti aage propagate hoti hai ("garbage in, garbage out")
- ❌ Order fixed hai, dynamic situation ke liye flexible nahi (uske liye supervisor, project 03)

## Pitfalls

1. **Endless QA ↔ Dev ping-pong** → `max_reworks` budget.
2. **Output format drift**: Architect ne file list ki jagah essay likh diya. Fix: `expected_output` strict rakho, zaroorat ho to structured output use karo.
3. **Cost blow-up**: har stage mein poori history bhejna. Fix: sirf declared context bhejo.
4. **Silent failure**: QA fail hua fir bhi "done" bol diya. Fix: `CrewResult.qa.passed` hamesha report karo.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Role / Task / Crew | `sequential_crew.py` → `Role`, `Task`, `SoftwareCrew` |
| Context passing | `Task.prompt(inputs, outputs)`: sirf `task.context` wale outputs |
| Output contract | `Task.expected_output` |
| Developer tool | `Workspace.as_tool()` → `save_file` |
| QA structured verdict | `QAVerdict` + `llm_json` in `_review()` |
| Bounded rework loop | `kickoff()` ka `while not verdict.passed and reworks < max_reworks` |
| Per-role models | `llm_for(role.key)` → `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`... |
| Offline fake | `offline_llm(qa_fails_first=True)` |
