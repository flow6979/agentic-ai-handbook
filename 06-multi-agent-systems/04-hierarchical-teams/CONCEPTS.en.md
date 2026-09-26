**Language:** [Hinglish](CONCEPTS.md) · English

# 04 · Hierarchical Teams: a manager of managers

## The short version

One supervisor (project 03) is fine for 3-4 workers. But with 15 workers a single manager's prompt gets far too long, routing starts going wrong, and the context overflows. Real companies solve this with **hierarchy**: CEO → team leads → engineers. Agents work the same way:

```
                        ┌─────────────────────┐
                        │   Launch Manager    │  L0: goal → team objectives
                        └──────────┬──────────┘
                ┌──────────────────┴──────────────────┐
                ▼                                     ▼
      ┌───────────────────┐                ┌────────────────────┐
      │  Marketing Lead   │  L1            │  Engineering Lead  │  objective → worker tasks
      └─────────┬─────────┘                └──────────┬─────────┘
         ┌──────┴───────┐                     ┌───────┴──────┐
         ▼              ▼                     ▼              ▼
    copywriter    social_media           backend_dev    qa_engineer   L2: the actual work
```

## Flow in two directions

```
DOWN (delegation / decomposition)          UP (roll-up / synthesis)
─────────────────────────────────          ─────────────────────────
goal                                        final launch plan
 └► team objectives   (manager)              ▲ the manager reads only team summaries
     └► worker tasks  (leads)                 ▲ the lead summarises worker outputs
         └► work      (workers)               ▲ raw output from workers
```

**Roll-up is the most important trick**: the manager doesn't get the raw output of 4 workers, only 3-line reports from 2 teams. That keeps the context at every level **small and bounded**, no matter how many workers sit below.

## Key concepts

### 1. Decomposition at every level
- Manager: `LaunchPlan{assignments:[{team, objective}]}`
- Lead: `TeamPlan{tasks:[{worker, task}]}`

Both come from structured output (`llm_json`), so the code can loop over them directly.

### 2. Span of control
Keep few direct reports (2-5) under each manager. If there are more, add another level. The same org-design rule applies to agents.

### 3. Validation of delegation (hallucination guard)
Sometimes the LLM invents a "legal" team or a "designer" worker that doesn't exist. The code checks (`if a.team not in TEAMS`) and **skips + records** them (`LaunchResult.skipped`). In that case nothing crashes, and nothing is silently ignored either.

### 4. Per-level model choice
`llm_for("manager")`, `llm_for("marketing_lead")`, `llm_for("copywriter")`. Give the planning/synthesis levels a strong model and the leaf workers a cheap fast model. In a hierarchy most calls happen at the leaves, so a cheap model there = big savings.

## Subtypes
| Subtype | What |
|---|---|
| **Static hierarchy** (this project) | The org chart is fixed in code (`TEAMS`) |
| **Dynamic hierarchy** | The manager decides at runtime how many sub-teams to create (spawns agents) |
| **Recursive decomposition** | If a task is too big, the worker becomes a sub-manager itself (recursion + depth limit) |
| **Hierarchical + parallel** | Teams run at the same time (marketing and engineering are independent) |
| **Hierarchical with escalation** | A stuck worker escalates to the lead, a stuck lead escalates to the manager |

## Trade-offs
- ✅ It scales: the context at each level is bounded
- ✅ Separation of concerns, each team's prompts can evolve independently
- ❌ Latency: levels × sequential calls (fix: run teams in parallel)
- ❌ **Telephone game**: every summary loses detail. The manager may never hear about something important.
- ❌ More LLM calls = more cost. Overkill for small jobs.

## Pitfalls
1. **Information loss in roll-up** → define the summary format (risks and blockers must be included).
2. **Duplicate work across teams** → the manager must give clearly non-overlapping objectives.
3. **Invented teams/workers** → validate + skip (implemented).
4. **Deep recursion** → keep a max depth.

## How this project uses it

| Concept | File / function |
|---|---|
| Org chart | `hierarchical_teams.py` → `TEAMS` dict |
| L0 decomposition | `LaunchManager.run()` → `llm_json(..., LaunchPlan)` |
| L1 decomposition | `TeamLead.execute()` → `llm_json(..., TeamPlan)` |
| Workers | `Agent(...)` inside `TeamLead.execute()` |
| Roll-up #1 (team report) | `TeamLead.execute()` → `self.llm.complete(... "3-line team report")` |
| Roll-up #2 (final plan) | `LaunchManager.run()` → final `complete()` with only summaries |
| Hallucination guard | `skipped` list, `LaunchResult.skipped` |
| Per-level models | `llm_factory("manager" / f"{team}_lead" / worker)` |
