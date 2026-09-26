**Language:** [Hinglish](CONCEPTS.md) · English

# 03 · Supervisor Team: one manager, many workers

## The short version

In the sequential crew (project 02) the order was **fixed up front**. In real work you often don't know what the next step will be: sometimes more research is needed, sometimes just a rewrite. In the **supervisor pattern** a manager LLM looks at what has happened so far in every round and decides **who works next**. This is LangGraph's "supervisor" architecture.

```
                  ┌────────────────┐
     ┌──────────► │   SUPERVISOR   │ ── {"next":"FINISH"} ──► final answer
     │            └───────┬────────┘
     │   {"next":"writer",│"instruction":"Draft the answer"}
     │         ┌──────────┼──────────┐
     │         ▼          ▼          ▼
     │   ┌──────────┐ ┌────────┐ ┌────────┐
     │   │researcher│ │ writer │ │ critic │
     │   │ +search  │ │        │ │        │
     │   └────┬─────┘ └───┬────┘ └───┬────┘
     │        └───────────┼──────────┘
     │                    ▼
     │           ┌────────────────┐
     └────────── │  shared BOARD  │  (every worker's output goes here)
                 └────────────────┘
```

A real run of this project:
```
round 1: supervisor → researcher   (needs facts)
round 2: supervisor → writer       (draft)
round 3: supervisor → critic       (review)  → "ISSUES: payback 6-10 yrs, not 3"
round 4: supervisor → writer       (fix)
round 5: supervisor → critic       → "APPROVED"
round 6: supervisor → FINISH
```

## Key concepts

### 1. Routing via structured output
The supervisor doesn't write free text. It returns a `Route` JSON:
```json
{"next": "writer", "reason": "facts ready", "instruction": "Draft the answer"}
```
`next` is a `Literal["researcher","writer","critic","FINISH"]`, so Pydantic rejects invalid names and `llm_json` makes the model retry. That way hallucinated worker names never cause a crash.

### 2. Shared vs private context
- The **supervisor** sees the whole BOARD, because it needs the big picture to decide.
- **Workers** only get the part relevant to their job (`_worker_input`):
  - researcher: question + instruction (no draft)
  - writer: research + critic feedback
  - critic: research + draft

This keeps every worker's prompt short, lowers cost, and stops workers from getting confused (protection against **context bleeding**).

### 3. Termination conditions (3 guards)
| Guard | Why |
|---|---|
| `FINISH` | Normal exit: the supervisor is satisfied |
| `max_rounds` | Cost ceiling; stop even if the supervisor never says FINISH |
| `max_same_worker` streak | **Stuck loop**: if the supervisor keeps calling the writer over and over, force a finish |

### 4. Worker = full agent
Every worker is an `agentkit.Agent` with its own tools and its own `max_steps`. The researcher can call the `search_notes` tool several times internally. The supervisor only sees the final output, so the nested loops stay encapsulated.

## Supervisor vs Sequential vs Swarm

| | Sequential (02) | **Supervisor (03)** | Swarm (07) |
|---|---|---|---|
| Who decides the next step | Code (fixed order) | A central manager LLM | The active agent itself (handoff) |
| Flexibility | Low | High | High |
| LLM calls | Workers only | Workers + 1 supervisor call per round | Agents only |
| Debugging | Easy | Medium (read the routing logs) | Hard |
| Single point of failure | No | The supervisor | No |

## Subtypes
- **Supervisor with tool-calling**: turn workers into tools like `transfer_to_researcher` and give them to the supervisor (LangGraph `create_supervisor`). Here we used JSON routing, which is more explicit.
- **Supervisor that also answers**: along with FINISH, the supervisor writes the final answer itself.
- **Hierarchical supervisor**: the workers are supervisors themselves (project 04).
- **Plan-then-delegate**: the supervisor first builds a full plan, then executes it (section 02: plan-and-execute).

## Pitfalls
1. **Infinite ping-pong** (writer ↔ critic never agree) → `max_rounds` and the streak guard.
2. **The supervisor starts doing the work itself** → make it clear in the prompt: "you only route".
3. **Cost blow-up**: the whole board goes to the supervisor every round, and it keeps growing. Fix: summarize old entries, or send only the latest entry per worker.
4. **Premature FINISH** → prompt: "FINISH only when the critic approved".
5. **Worker scope creep**: the researcher writes the final answer → add a forbidden rule to the role prompt.

## How this project uses it

| Concept | File / function |
|---|---|
| Routing schema | `supervisor_team.py` → `Route` (Pydantic, Literal) |
| Supervisor decision | `SupervisorTeam.run()` → `llm_json(self.supervisor_llm, ..., Route)` |
| Shared board | `BoardEntry`, `self.board`, `_board_text()` |
| Private worker context | `_worker_input(worker, ...)` |
| Worker agents + tools | `__post_init__` → `Agent(...)`, `search_notes` tool |
| Termination guards | `FINISH`, `max_rounds`, `max_same_worker` → `TeamResult.stopped_reason` |
| Per-role LLMs | `llm_for("supervisor")`, `llm_for("researcher")`... |
