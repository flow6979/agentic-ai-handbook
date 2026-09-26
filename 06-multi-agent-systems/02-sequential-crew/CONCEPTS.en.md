**Language:** [Hinglish](CONCEPTS.md) · English

# 02 · Sequential Crew: an assembly line of agents

## The short version

Picture a software team: the PM writes requirements, the Architect produces a design, the Developer writes code, and QA checks it. Each person's output becomes the next person's input. A **sequential crew** is exactly that: agents in a fixed order, one after another. CrewAI's `Process.sequential` is built on this idea. Here we build it from scratch.

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
                                                  (up to max_reworks)
                                                     passed=true ──► DONE
```

## 3 building blocks

| Block | What it is | Code |
|---|---|---|
| **Role** | Who (title, goal, backstory, tools) | `Role` dataclass |
| **Task** | What to do: `description`, `expected_output`, which `role`, and which tasks it needs as `context` | `Task` dataclass |
| **Crew** | Runs the tasks in order and stores their outputs | `SoftwareCrew.kickoff()` |

### Task ≠ Role (important!)

Role = **who**, Task = **what**. One role can do several tasks (Developer: "implement" and "fix"). That is why they are kept separate.

### `expected_output` = contract

Every task states the shape its output must have ("3-5 user stories with acceptance criteria"). The next role depends on that shape. Without this contract the Architect would not know what to look for in the PM's output.

## Context passing (the most important concept)

```
outputs = {}                         # shared "memory" of the crew
stories  ← PM(task)                  outputs["stories"]
design   ← Architect(task + stories) outputs["design"]
code     ← Dev(task + stories + design)
```

`Task.context=["stories", "design"]` explicitly says which earlier outputs are needed. **Don't send everything to everyone**:

- ❌ **Context bleeding**: the Developer gets all of the PM's thinking and the Architect's rough notes, so the prompt gets long, focus is lost and cost goes up.
- ✅ Send only the declared dependencies. The test `test_context_passing_only_declared_dependencies` checks exactly this.

## Tools per role

Only the Developer has the `save_file` tool (`Workspace.as_tool()`). The PM and QA don't need to write files, so they don't get the tool. That is **least privilege**.

## Feedback loop (sequential + one loop)

In a purely sequential pipeline mistakes keep flowing forward. So after QA there is a **bounded rework loop**:
- QA returns a structured verdict: `QAVerdict(passed, issues)`
- fail → a "fix" task goes to the Developer with the issues, at most `max_reworks` times
- Budget used up? Stop and report `passed=false` (an **honest failure**, not an infinite loop)

## Subtypes / variations

| Variation | What | When |
|---|---|---|
| **Pure sequential** | A→B→C, no loop | Simple content pipelines |
| **Sequential + review loop** (this project) | A reviewer at the end, bounded rework | When quality matters |
| **Hierarchical process** | A manager decides which task goes to whom | The order isn't fixed up front (project 04) |
| **Parallel stages** | Independent tasks run together | To cut latency (section 02 parallelization) |
| **Human checkpoint** | A human approves after some stage | High-stakes output |

## Trade-offs

- ✅ Predictable, easy to debug, and you can inspect every stage's output
- ✅ Each role's prompt stays short and focused
- ❌ Latency = the sum of all stages
- ❌ Early mistakes propagate forward ("garbage in, garbage out")
- ❌ The order is fixed, so it is not flexible for dynamic situations (use a supervisor for that, project 03)

## Pitfalls

1. **Endless QA ↔ Dev ping-pong** → the `max_reworks` budget.
2. **Output format drift**: the Architect wrote an essay instead of a file list. Fix: keep `expected_output` strict, and use structured output if needed.
3. **Cost blow-up**: sending the full history to every stage. Fix: send only the declared context.
4. **Silent failure**: QA failed but the crew still said "done". Fix: always report `CrewResult.qa.passed`.

## How this project uses it

| Concept | File / function |
|---|---|
| Role / Task / Crew | `sequential_crew.py` → `Role`, `Task`, `SoftwareCrew` |
| Context passing | `Task.prompt(inputs, outputs)`: only the outputs listed in `task.context` |
| Output contract | `Task.expected_output` |
| Developer tool | `Workspace.as_tool()` → `save_file` |
| QA structured verdict | `QAVerdict` + `llm_json` in `_review()` |
| Bounded rework loop | the `while not verdict.passed and reworks < max_reworks` in `kickoff()` |
| Per-role models | `llm_for(role.key)` → `LLM_MODEL_PM`, `LLM_MODEL_DEVELOPER`... |
| Offline fake | `offline_llm(qa_fails_first=True)` |
