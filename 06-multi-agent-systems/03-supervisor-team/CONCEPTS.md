**Language:** Hinglish · [English](CONCEPTS.en.md)

# 03 · Supervisor Team — Ek manager, kai workers

## Seedhi baat

Sequential crew (project 02) mein order **pehle se fixed** tha. Lekin real kaam mein pata nahi hota ki agla step kya hoga: kabhi research dobara chahiye, kabhi sirf rewrite. **Supervisor pattern** mein ek manager LLM har round mein dekhta hai ki ab tak kya hua, aur decide karta hai ki **agla kaun** kaam karega. LangGraph ka "supervisor" architecture yahi hai.

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
     └────────── │  shared BOARD  │  (har worker ka output yahan)
                 └────────────────┘
```

Is project ka ek real run:
```
round 1: supervisor → researcher   (facts chahiye)
round 2: supervisor → writer       (draft)
round 3: supervisor → critic       (review)  → "ISSUES: payback 6-10 yrs, not 3"
round 4: supervisor → writer       (fix)
round 5: supervisor → critic       → "APPROVED"
round 6: supervisor → FINISH
```

## Key concepts

### 1. Routing via structured output
Supervisor free text nahi likhta. Woh `Route` JSON deta hai:
```json
{"next": "writer", "reason": "facts ready", "instruction": "Draft the answer"}
```
`next` ek `Literal["researcher","writer","critic","FINISH"]` hai, isliye Pydantic invalid naam reject kar deta hai aur `llm_json` model se retry karwata hai. Isse hallucinated worker names se crash nahi hota.

### 2. Shared vs private context
- **Supervisor** ko poora BOARD dikhta hai, kyunki decide karne ke liye big picture chahiye.
- **Workers** ko sirf unke kaam ka hissa milta hai (`_worker_input`):
  - researcher: question + instruction (draft nahi)
  - writer: research + critic feedback
  - critic: research + draft

Isse har worker ka prompt chhota rehta hai, cost kam hoti hai, aur worker confuse nahi hota (**context bleeding** se bachaav).

### 3. Termination conditions (3 guards)
| Guard | Kyun |
|---|---|
| `FINISH` | Normal exit: supervisor satisfied hai |
| `max_rounds` | Cost ceiling; supervisor kabhi FINISH na bole tab bhi rukna hai |
| `max_same_worker` streak | **Stuck loop**: supervisor baar baar writer ko hi bulaye to force finish |

### 4. Worker = full agent
Har worker ek `agentkit.Agent` hai, apne tools aur apne `max_steps` ke saath. Researcher andar se `search_notes` tool ko multiple baar call kar sakta hai. Supervisor ko sirf final output dikhta hai, isliye nested loops encapsulated rehte hain.

## Supervisor vs Sequential vs Swarm

| | Sequential (02) | **Supervisor (03)** | Swarm (07) |
|---|---|---|---|
| Kaun decide kare agla step | Code (fixed order) | Central manager LLM | Active agent khud (handoff) |
| Flexibility | Kam | Zyada | Zyada |
| LLM calls | Sirf workers | Workers + har round 1 supervisor call | Sirf agents |
| Debug | Aasaan | Medium (routing logs dekho) | Mushkil |
| Single point of failure | Nahi | Supervisor | Nahi |

## Subtypes
- **Supervisor with tool-calling**: workers ko `transfer_to_researcher` jaise tools bana ke supervisor ko de do (LangGraph `create_supervisor`). Yahan humne JSON routing use kiya jo zyada explicit hai.
- **Supervisor that also answers**: FINISH ke saath final answer bhi supervisor khud likhe.
- **Hierarchical supervisor**: workers khud supervisors hain (project 04).
- **Plan-then-delegate**: supervisor pehle poora plan banaye, phir execute kare (section 02: plan-and-execute).

## Pitfalls
1. **Infinite ping-pong** (writer ↔ critic kabhi agree na karein) → `max_rounds` aur streak guard.
2. **Supervisor khud kaam karne lage** → prompt mein clear karo ki "you only route".
3. **Cost blow-up**: har round mein supervisor ko poora board jaata hai, jo lamba hota jaata hai. Fix: purane entries summarize karo ya sirf latest per worker bhejo.
4. **Premature FINISH** → prompt: "FINISH only when the critic approved".
5. **Worker scope creep**: researcher final answer likh de → forbidden rule role prompt mein.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Routing schema | `supervisor_team.py` → `Route` (Pydantic, Literal) |
| Supervisor decision | `SupervisorTeam.run()` → `llm_json(self.supervisor_llm, ..., Route)` |
| Shared board | `BoardEntry`, `self.board`, `_board_text()` |
| Private worker context | `_worker_input(worker, ...)` |
| Worker agents + tools | `__post_init__` → `Agent(...)`, `search_notes` tool |
| Termination guards | `FINISH`, `max_rounds`, `max_same_worker` → `TeamResult.stopped_reason` |
| Per-role LLMs | `llm_for("supervisor")`, `llm_for("researcher")`... |
