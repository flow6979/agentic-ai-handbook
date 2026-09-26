**Language:** [Hinglish](CONCEPTS.md) · English

# 01 · Role Design Basics: what is a "role", really?

## The short version

In a multi-agent system every agent plays a **role**, just like different people do different jobs in an office. Technically a "role" is not magic: it is just a bundle of **system prompt + tools + rules**. Give the same LLM different role prompts and it behaves like a different "person".

```
            one LLM (or several different LLMs)
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
 ┌─────────┐      ┌─────────┐      ┌─────────┐
 │ Writer  │      │ Editor  │      │ Critic  │
 │ prompt A│      │ prompt B│      │ prompt C│
 │ tools A │      │ tools B │      │ tools C │
 └─────────┘      └─────────┘      └─────────┘
```

## The 6 parts of a good role

| Part | What it is | Example (Editor) | Why it matters |
|---|---|---|---|
| **Persona** | Who it is | "a strict but fair copy editor" | Sets the tone and judgement |
| **Goal** | What it must achieve | "Decide if draft is accurate, clear, <120 words" | A measurable goal = focused output |
| **Backstory** | Background context | "wrote docs for 10 years, hates jargon" | Shapes subtle decisions (optional) |
| **Tools** | What it can use | researcher → `search_notes` | Least privilege: only what it needs |
| **Allowed / Forbidden actions** | What it may do / must NOT do | "MUST NOT rewrite whole article" | Prevents **role drift** |
| **Output contract** | The exact output format | `{"approved": bool, "feedback": str}` | The next agent/code depends on it |

## Role → system prompt (template)

In this project `Role.system_prompt()` renders every role with the same template:

```
ROLE: Editor
You are a strict but fair copy editor.
GOAL: Decide if the draft is accurate, clear and under 120 words; give actionable feedback
YOU MAY: review; approve; request changes
YOU MUST NOT: rewrite the whole article yourself
OUTPUT FORMAT: JSON: {"approved": bool, "feedback": "..."}
Stay strictly in your role. If a request is outside your role, say so briefly.
```

**Why a template?** Every role keeps the same structure, prompts are easy to review, and creating a new role is just a matter of filling in data.

## Flow of the 2-role example: Writer + Editor

```
 topic
   │
   ▼
┌────────┐  draft   ┌────────┐  {"approved": false, "feedback": "..."}
│ Writer │────────► │ Editor │──────────────┐
└────────┘          └────────┘              │
   ▲                     │ approved=true    │
   │                     ▼                  │
   │                  FINAL                 │
   └──── draft + feedback (revise) ◄────────┘
         (up to max_revisions)
```

- The Writer only sees the **draft + feedback**, not the whole history, so its context stays small and focused.
- The Editor's output is **structured** (Pydantic `EditorVerdict`), so the code decides with a plain if/else. Nobody has to parse text and guess.
- **Termination**: either the draft is approved OR the revision budget runs out. Without a budget the writer and editor would ping-pong forever.

## Multi-LLM: a different model per role

`llm_for(role)` first checks the `LLM_MODEL_WRITER` / `LLM_MODEL_EDITOR` env vars, and falls back to `LLM_MODEL`:

```
LLM_MODEL=groq:llama-3.3-70b-versatile        # default for everyone
LLM_MODEL_EDITOR=anthropic:claude-sonnet-5    # a strong model for the judge/reviewer
```

A common pattern: **a cheap, fast model generates and a strong model reviews**. That keeps cost down and quality up.

## Anti-patterns (don't do these)

1. **Vague role**: `Role("Helper", "a helpful AI", "help with everything")` (`BAD_ROLE` in the code). The model has no idea when to stop or what not to do, so it will drift out of role.
2. **Overlapping roles**: two roles with the same goal, for example a "Reviewer" and a "Critic" that do the same job. You get duplicated work, and one output overwrites the other.
3. **Self-approval**: the writer approves its own work. That is why "approve your own work" is in `forbidden_actions`.
4. **Missing output contract**: the next agent has to parse free text, which makes everything fragile.
5. **Giving every tool to everyone**: a security risk, and the model may also pick the wrong tool.
6. **Too many roles**: every role = extra LLM calls = extra cost/latency. Try a single agent first and split only when you need to.

## When to use multiple roles, and when not to

- ✅ When the work needs **different perspectives** (create vs critique), or different tools/permissions.
- ✅ When cramming every instruction into one prompt is hurting quality.
- ❌ For simple Q&A, where one agent with tools is enough.
- ❌ When latency is critical, because every role hop is an extra LLM round-trip.

## How this project uses it

| Concept | File / function |
|---|---|
| The 6 parts of a role | `role_design.py` → `@dataclass Role` |
| Role → prompt template | `Role.system_prompt()` |
| Per-role model | `llm_for(role)` |
| Writer/Editor roles | `WRITER`, `EDITOR` constants |
| Structured review | `EditorVerdict` + `llm_json(...)` |
| Revision loop + termination | `write_with_editor(..., max_revisions=2)` |
| Offline fake (role-aware) | `offline_llm()`: answers based on the `ROLE:` line in the system prompt |
| Anti-pattern example | `BAD_ROLE` |
