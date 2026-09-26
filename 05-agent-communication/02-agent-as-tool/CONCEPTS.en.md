**Language:** [Hinglish](CONCEPTS.md) · English

# 02 · Agent-as-Tool (turn an agent into a function)

## Basic idea

We already know that an agent calls **tools** (`calculate`, `search`...).
Now imagine: what if the tool is itself a **whole agent**?

```
 From the manager agent's view:          What is actually inside:

   ask_math_expert(task="...")    ═══►   ┌─────────── MathExpert Agent ───────────┐
          │                              │ system: "You are a math expert"        │
          │                              │ tools: calculate, percent_change       │
          │                              │ loop: LLM → tool → LLM → answer        │
          ▼                              └────────────────────────────────────────┘
   {"agent":"math_expert","ok":true,
    "output":"26.32%","steps":2,...}
```

To the manager this is just a function call. This is called **"agents as tools"** or the
**"manager pattern"**. `agent.as_tool()` in the OpenAI Agents SDK, the "tool-calling supervisor" in LangGraph,
and subagents in Claude Code all run on this idea.

## The full flow

```
 User: "Sales 950→1200, growth %? And write a post"
   │
   ▼
┌─────────┐ 1. ask_math_expert(task="% change 950→1200")
│ Manager │──────────────────────────────────────────►┌────────────┐
│  (LLM)  │                                            │ MathExpert │─► percent_change(950,1200)
│         │◄──────── {"output":"26.32%"} ──────────────│  (LLM)     │◄─ 26.32
│         │                                            └────────────┘
│         │ 2. ask_copywriter(task="post: grew 26.32%")
│         │──────────────────────────────────────────►┌────────────┐
│         │◄── {"output":{"headline","body"}} ─────────│ Copywriter │
│         │                                            └────────────┘
│         │ 3. combine both results into the final answer
└─────────┘
   │
   ▼
 Final answer to the user
```

## Three core concepts

### 1) Context isolation

The specialist receives **only the `task` string**, not the manager's whole chat.

```
 Manager's context:    [system, user("SECRET-ID-42 ..."), tool calls, results ...]  ← large
 Specialist's context: [system, user("pct change 950 -> 1200")]                     ← small
```

**Benefits:**
- fewer tokens, so it is cheaper and faster
- the specialist does not get confused and stays focused
- sensitive data only goes where it is needed

**The cost:** the manager has to write the task **self-contained** (put every fact into the task).
That is why the tool description says *"Include all needed facts."*

### 2) Structured result envelope

The sub-agent's output is not raw text; it is wrapped in JSON:

```json
{"agent": "copywriter", "ok": true, "output": {"headline": "...", "body": "..."}, "steps": 1, "tokens": 52}
```

- `ok` tells you whether the work finished or stopped at max_steps
- with `expect_json=True`, the output is parsed as JSON before being sent back
- `steps` / `tokens` let the manager (and you) see the cost

### 3) Failure containment

If the sub-agent crashes, the provider is down, or it gets stuck in a loop, the manager receives an error JSON
(`ok: false`), not an exception. The manager can decide: retry, use another specialist, or
tell the user.

## Agent-as-Tool vs Handoff (project 03)

| | Agent-as-Tool | Handoff |
|---|---|---|
| Control | Stays with the manager | Moves to the new agent |
| Context given to the specialist | Only the task | The whole conversation |
| Who talks to the user | Always the manager | Whichever agent is active |
| Analogy | The boss delegates work and collects the result | A call center transferring a call |
| Best for | Sub-tasks, parallel research, calculations | Different departments, long conversations |

## Variants (subtypes)

- **Single specialist tool**: one expert (e.g. a SQL agent)
- **Many specialists** (this project): the manager routes between them
- **Nested**: agent-tools inside a specialist too (a hierarchy, see section 06)
- **Parallel**: the manager makes several tool calls in one turn and they all run together
- **Different models**: a large model for the manager, small/cheap models for specialists (cost optimization)

## When to use it / when not to

**Use it:** when the work splits into sub-tasks needing different skills, and the final answer has to be
combined in one place.

**Do not use it:** when the specialist needs the whole conversation (use a handoff), or the job is so small
that a normal tool is enough. Every agent-tool call = an extra LLM loop = extra latency and cost.

## Pitfalls

- The manager forgets facts in the task, so the specialist does the wrong thing → instruct it in the description
- The specialist's long output fills the manager's context → ask for a summary/structured output
- Recursion (A's tool is B, B's tool is A) → keep a depth limit
- Specialists' tokens stay hidden → report `tokens` in every result

## How this project uses it

| Concept | Where |
|---|---|
| Agent → Tool wrapper | `agent_as_tool.py` → `agent_as_tool()` |
| Context isolation (a fresh `agent.run(task)`) | `agent_as_tool.py` → `run()` |
| Structured envelope + `expect_json` | `agent_as_tool.py` |
| Failure containment (try/except, `ok` flag) | `agent_as_tool.py` |
| Specialists (math with tools, copywriter JSON) | `agent_as_tool_team.py` → `build_team()` |
| Safe calculator (no `eval`) | `agent_as_tool_team.py` → `_safe_eval` |
| Isolation proven in a test | `test_agent_as_tool.py` → `SECRET-ID-42` assert |
