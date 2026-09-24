# 02 · Agent-as-Tool (Agent ko function bana do)

## Basic idea

Hum pehle se jaante hain ki agent **tools** call karta hai (`calculate`, `search`...).
Ab socho: agar tool khud ek **poora agent** ho?

```
 Manager agent ki nazar se:              Asal mein andar:

   ask_math_expert(task="...")    ═══►   ┌─────────── MathExpert Agent ───────────┐
          │                              │ system: "You are a math expert"        │
          │                              │ tools: calculate, percent_change       │
          │                              │ loop: LLM → tool → LLM → answer        │
          ▼                              └────────────────────────────────────────┘
   {"agent":"math_expert","ok":true,
    "output":"26.32%","steps":2,...}
```

Manager ke liye yeh bas ek function call hai. Isko **"agents as tools"** ya
**"manager pattern"** kehte hain. OpenAI Agents SDK mein `agent.as_tool()`, LangGraph mein
"tool-calling supervisor", aur Claude Code mein subagents isi idea pe chalte hain.

## Poora flow

```
 User: "Sales 950→1200, growth %? Aur ek post likho"
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
│         │ 3. dono results jodke final answer
└─────────┘
   │
   ▼
 User ko final answer
```

## Teen core concepts

### 1) Context isolation

Specialist ko **sirf `task` string** milti hai, manager ki poori chat nahi.

```
 Manager ka context:  [system, user("SECRET-ID-42 ..."), tool calls, results ...]  ← bada
 Specialist ka context: [system, user("pct change 950 -> 1200")]                   ← chhota
```

**Faayde:**
- kam tokens, isliye sasta aur fast
- specialist confuse nahi hota, focused rehta hai
- sensitive data sirf wahan jata hai jahan zaroorat ho

**Keemat:** manager ko task **self-contained** likhna padta hai (saare facts task mein daalo).
Isliye tool description mein likha hai *"Include all needed facts."*

### 2) Structured result envelope

Sub-agent ka output raw text nahi, JSON mein wrap hota hai:

```json
{"agent": "copywriter", "ok": true, "output": {"headline": "...", "body": "..."}, "steps": 1, "tokens": 52}
```

- `ok` batata hai ki kaam poora hua ya max_steps pe ruka
- `expect_json=True` ho to output JSON parse karke bhejte hain
- `steps` / `tokens` se manager (aur tum) cost dekh sakte ho

### 3) Failure containment

Sub-agent crash ho, provider down ho, ya loop mein phas jaye, to manager ko error JSON milta hai
(`ok: false`), exception nahi. Manager decide kar sakta hai: retry kare, dusra specialist le, ya
user ko bataye.

## Agent-as-Tool vs Handoff (project 03)

| | Agent-as-Tool | Handoff |
|---|---|---|
| Control | Manager ke paas rehta hai | Naye agent ko chala jata hai |
| Specialist ko context | Sirf task | Poori conversation |
| User se baat kaun karta hai | Hamesha manager | Jo active agent hai |
| Analogy | Boss kaam delegate karke result leta hai | Call center call transfer |
| Best for | Sub-tasks, parallel research, calculations | Different departments, lambi conversation |

## Variants (subtypes)

- **Single specialist tool**: ek expert (e.g. SQL agent)
- **Many specialists** (yeh project): manager route karta hai
- **Nested**: specialist ke andar bhi agent-tools (hierarchy, section 06 dekho)
- **Parallel**: manager ek hi turn mein kai tool calls kare, sab saath chalein
- **Different models**: manager bada model, specialists chhote/saste model (cost optimization)

## Kab use karein / kab nahi

**Use karo:** kaam alag-alag skill wale sub-tasks mein bat-ta hai, aur final jawab ek jagah
combine karna hai.

**Mat use karo:** specialist ko poori conversation chahiye (handoff lo), ya kaam itna chhota hai
ki ek normal tool kaafi hai. Har agent-tool call = extra LLM loop = extra latency aur cost.

## Pitfalls

- Manager task mein facts bhool jaata hai, isliye specialist galat kaam karta hai → description mein instruct karo
- Specialist ka lamba output manager ka context bhar deta hai → summary/structured output mango
- Recursion (A tool B, B tool A) → depth limit rakho
- Specialists ke tokens hidden rehte hain → har result mein `tokens` report karo

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Agent → Tool wrapper | `agent_as_tool.py` → `agent_as_tool()` |
| Context isolation (`agent.run(task)` fresh) | `agent_as_tool.py` → `run()` |
| Structured envelope + `expect_json` | `agent_as_tool.py` |
| Failure containment (try/except, `ok` flag) | `agent_as_tool.py` |
| Specialists (math with tools, copywriter JSON) | `agent_as_tool_team.py` → `build_team()` |
| Safe calculator (no `eval`) | `agent_as_tool_team.py` → `_safe_eval` |
| Isolation proven in test | `test_agent_as_tool.py` → `SECRET-ID-42` assert |
