# 01 · Role Design Basics — "Role" hota kya hai?

## Seedhi baat

Multi-agent system mein har agent ek **role** nibhata hai, jaise office mein alag log alag kaam karte hain. Technically "role" koi jaadu nahi hai: yeh bas **system prompt + tools + rules** ka ek bundle hai. Ek hi LLM ko alag role prompts do to woh alag "insaan" jaisa behave karta hai.

```
            ek hi LLM (ya alag alag LLMs)
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
 ┌─────────┐      ┌─────────┐      ┌─────────┐
 │ Writer  │      │ Editor  │      │ Critic  │
 │ prompt A│      │ prompt B│      │ prompt C│
 │ tools A │      │ tools B │      │ tools C │
 └─────────┘      └─────────┘      └─────────┘
```

## Ek achhe role ke 6 hisse

| Hissa | Kya hai | Example (Editor) | Kyun zaroori |
|---|---|---|---|
| **Persona** | Kaun hai | "a strict but fair copy editor" | Tone aur judgement set karta hai |
| **Goal** | Kya achieve karna hai | "Decide if draft is accurate, clear, <120 words" | Measurable goal = focused output |
| **Backstory** | Background context | "10 saal docs likhe, jargon se nafrat" | Subtle decisions shape karta hai (optional) |
| **Tools** | Kya use kar sakta hai | researcher → `search_notes` | Least privilege: jo chahiye sirf wahi |
| **Allowed / Forbidden actions** | Kya kar sakta hai / kya NAHI | "MUST NOT rewrite whole article" | **Role drift** rokta hai |
| **Output contract** | Output ka exact format | `{"approved": bool, "feedback": str}` | Agla agent/code isi pe depend karta hai |

## Role → System prompt (template)

Is project mein `Role.system_prompt()` har role ko same template se render karta hai:

```
ROLE: Editor
You are a strict but fair copy editor.
GOAL: Decide if the draft is accurate, clear and under 120 words; give actionable feedback
YOU MAY: review; approve; request changes
YOU MUST NOT: rewrite the whole article yourself
OUTPUT FORMAT: JSON: {"approved": bool, "feedback": "..."}
Stay strictly in your role. If a request is outside your role, say so briefly.
```

**Template kyun?** Sab roles ka structure same rahega, prompts review karna aasaan hoga, aur naya role banana bas data bharna reh jaata hai.

## 2-role example ka flow: Writer + Editor

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
         (max_revisions tak)
```

- Writer sirf **draft + feedback** dekhta hai, poori history nahi, isliye context chhota aur focused rehta hai.
- Editor ka output **structured** (Pydantic `EditorVerdict`) hai, isliye code if/else se decide karta hai. Kisi text ko parse karke andaza nahi lagana padta.
- **Termination**: approve ho jaaye YA revision budget khatam ho jaaye. Bina budget ke writer aur editor hamesha ping-pong karte rahenge.

## Multi-LLM: har role ka alag model

`llm_for(role)` pehle `LLM_MODEL_WRITER` / `LLM_MODEL_EDITOR` env dekhta hai, na mile to `LLM_MODEL`:

```
LLM_MODEL=groq:llama-3.3-70b-versatile        # default sab ke liye
LLM_MODEL_EDITOR=anthropic:claude-sonnet-5    # judge/reviewer ko strong model
```

Common pattern: **sasta + fast model generate kare, strong model review kare**. Isse cost kam rehti hai aur quality bhi.

## Anti-patterns (yeh mat karo)

1. **Vague role**: `Role("Helper", "a helpful AI", "help with everything")` (`BAD_ROLE` in code). Model ko pata hi nahi kab rukna hai ya kya nahi karna, isliye woh role drift karega.
2. **Overlapping roles**: do roles jinka goal same hai, jaise "Reviewer" aur "Critic" dono ek hi kaam karte hain. Isse duplicate kaam hota hai aur ek ka output doosra overwrite karta hai.
3. **Self-approval**: writer khud apna kaam approve kare. Isliye `forbidden_actions` mein "approve your own work" rakha hai.
4. **Output contract missing**: agla agent free text parse karega aur fragile ho jayega.
5. **Sab tools sabko dena**: security risk, aur model galat tool bhi chuns sakta hai.
6. **Bahut saare roles**: har role = extra LLM calls = extra cost/latency. Pehle 1 agent try karo, zaroorat pe hi split karo.

## Kab multi-role? Kab nahi?

- ✅ Jab kaam mein **alag perspectives** chahiye (create vs critique), ya alag tools/permissions.
- ✅ Jab ek prompt mein sab instructions thoos dene se quality gir rahi ho.
- ❌ Simple Q&A ke liye, jahan ek agent + tools kaafi hai.
- ❌ Jab latency critical ho, kyunki har role hop ek extra LLM round-trip hai.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Role ke 6 hisse | `role_design.py` → `@dataclass Role` |
| Role → prompt template | `Role.system_prompt()` |
| Per-role model | `llm_for(role)` |
| Writer/Editor roles | `WRITER`, `EDITOR` constants |
| Structured review | `EditorVerdict` + `llm_json(...)` |
| Revision loop + termination | `write_with_editor(..., max_revisions=2)` |
| Offline fake (role-aware) | `offline_llm()`: system prompt ka `ROLE:` dekh ke jawab |
| Anti-pattern example | `BAD_ROLE` |
