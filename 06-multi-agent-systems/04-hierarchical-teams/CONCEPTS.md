**Language:** Hinglish · [English](CONCEPTS.en.md)

# 04 · Hierarchical Teams — Manager of managers

## Seedhi baat

Ek supervisor (project 03) 3-4 workers tak theek hai. Lekin 15 workers ho jaayein to ek manager ka prompt bahut lamba ho jaata hai, routing galat hone lagti hai, aur context overflow hota hai. Real companies yeh problem **hierarchy** se solve karti hain: CEO → team leads → engineers. Agents mein bhi yahi:

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
    copywriter    social_media           backend_dev    qa_engineer   L2: actual kaam
```

## Do directions ka flow

```
DOWN (delegation / decomposition)          UP (roll-up / synthesis)
─────────────────────────────────          ─────────────────────────
goal                                        final launch plan
 └► team objectives   (manager)              ▲ manager padhta hai sirf team summaries
     └► worker tasks  (leads)                 ▲ lead summarise karta hai worker outputs
         └► work      (workers)               ▲ workers ka raw output
```

**Roll-up sabse important trick hai**: manager ko 4 workers ka raw output nahi milta, sirf 2 teams ke 3-line reports milte hain. Isse har level ka context **chhota aur bounded** rehta hai, chahe neeche kitne bhi workers hon.

## Key concepts

### 1. Decomposition at every level
- Manager: `LaunchPlan{assignments:[{team, objective}]}`
- Lead: `TeamPlan{tasks:[{worker, task}]}`

Dono structured output (`llm_json`) se aate hain, isliye code seedha loop chala sakta hai.

### 2. Span of control
Har manager ke neeche kam direct reports (2-5) rakho. Zyada hon to ek aur level daalo. Yahi org design ka rule agents pe bhi lagta hai.

### 3. Validation of delegation (hallucination guard)
LLM kabhi "legal" team ya "designer" worker invent kar deta hai jo exist hi nahi karte. Code check karta hai (`if a.team not in TEAMS`) aur unhe **skip + record** karta hai (`LaunchResult.skipped`). Is case mein crash nahi hota, aur chupke se ignore bhi nahi hota.

### 4. Per-level model choice
`llm_for("manager")`, `llm_for("marketing_lead")`, `llm_for("copywriter")`. Planning/synthesis wale levels ko strong model do, leaf workers ko sasta fast model. Hierarchy mein zyada calls leaf pe hoti hain, isliye wahan sasta model = badi bachat.

## Subtypes
| Subtype | Kya |
|---|---|
| **Static hierarchy** (yeh project) | Org chart code mein fixed (`TEAMS`) |
| **Dynamic hierarchy** | Manager runtime pe decide kare kitne sub-teams banane hain (spawn agents) |
| **Recursive decomposition** | Task bahut bada ho to worker khud sub-manager ban jaaye (recursion + depth limit) |
| **Hierarchical + parallel** | Teams ek saath chalein (marketing aur engineering independent hain) |
| **Hierarchical with escalation** | Worker atke to lead ko, lead atke to manager ko escalate kare |

## Trade-offs
- ✅ Scale karta hai: har level ka context bounded
- ✅ Separation of concerns, har team ke prompts alag evolve ho sakte hain
- ❌ Latency: levels × sequential calls (fix: teams ko parallel chalao)
- ❌ **Telephone game**: har summary mein detail gum hoti hai. Manager ko kuch zaroori baat pata hi nahi chalti.
- ❌ Zyada LLM calls = zyada cost. Chhote kaam ke liye overkill hai.

## Pitfalls
1. **Information loss in roll-up** → summaries ka format define karo (risks, blockers zaroor include ho).
2. **Duplicate work across teams** → manager objectives clearly non-overlapping de.
3. **Invented teams/workers** → validate + skip (implemented).
4. **Deep recursion** → max depth rakho.

## Is project mein kaise use ho raha hai

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
