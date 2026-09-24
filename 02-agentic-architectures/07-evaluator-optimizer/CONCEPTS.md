# Evaluator-Optimizer

## 1. Concept kya hai?

Do roles: **Generator** (likhta hai) aur **Evaluator** (rubric pe judge karta hai aur specific feedback deta hai).
Feedback generator ko wapas jaata hai, woh sudhaarta hai. Loop tab tak chalta hai jab tak quality bar pass na ho
ya budget khatam na ho. Bilkul writer + editor ki tarah.

```
            ┌───────────────────────────────────────────────────────────────┐
            │                                                               │
   brief ──►│ GENERATOR ──► draft ──► HARD CHECKS ──fail──┐                 │
            │    ▲                    (code: <=280 chars, │                 │
            │    │                     <=2 hashtags)      │                 │
            │    │                         │ pass         │                 │
            │    │                         ▼              │                 │
            │    │                    EVALUATOR (LLM)     │                 │
            │    │                    rubric: clarity,    │                 │
            │    │                    hook, cta (1-10)    │                 │
            │    │                         │              │                 │
            │    └──── feedback ◄──────────┴──────────────┘                 │
            │                                                               │
            └── STOP when: (1) sab scores >= threshold  -> "passed"        ─┘
                           (2) max_iters                -> "max_iters"
                           (3) score `patience` baar se nahi badha -> "no_improvement"
                 return: BEST attempt (last nahi!)
```

## 2. Reflection se farak? (06-reflection dekho)

| | Reflection | Evaluator-Optimizer |
|---|---|---|
| Kaun critique karta hai | Same agent khud ko | Alag evaluator (alag prompt, ideally alag model) |
| Criteria | Open "kya improve ho sakta hai?" | **Explicit rubric** + scores |
| Stop | Often fixed rounds | Threshold / no-improvement / budget |

Evaluator-optimizer tab chamakta hai jab **clear evaluation criteria** hon aur iteration se measurable fayda ho
(translation nuance, copy writing, code jo tests pass kare, SQL jo query validate kare).

## 3. Evaluator ke types

```
 cheapest ─────────────────────────────────────────────────────────► costliest
 ┌─────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌──────────────┐
 │ Code checks │   │ Execution / tool │   │ LLM-as-judge    │   │ Human review │
 │ length,     │   │ tests pass? SQL  │   │ rubric scores + │   │              │
 │ regex,      │   │ runs? link 200?  │   │ feedback        │   │              │
 │ schema      │   │                  │   │                 │   │              │
 └─────────────┘   └──────────────────┘   └─────────────────┘   └──────────────┘
   deterministic      ground truth           subjective quality     final authority
```
**Order matters**: pehle sasti deterministic checks. Fail ho to LLM judge pe paisa mat kharcho
(`optimize()` yahi karta hai: hard fail -> evaluator skip).

## 4. Stop criteria (teeno zaroori)

1. **Passed**: har criterion `>= threshold`. (Total score nahi, har criterion: ek bahut weak criterion ko doosre ka high score chhupa na de.)
2. **max_iters**: cost/latency ka hard cap.
3. **No improvement (patience)**: LLMs kabhi kabhi "improve" karte karte bigaadte hain (oscillation). Isliye **best** attempt return karo, last nahi.

## 5. Kab use karein / kab nahi

Use karo:
- Clear rubric hai aur human feedback se output sach mein better hota hai.
- Pehla draft aksar "almost" hota hai.

Mat karo:
- Evaluator reliable nahi (vague criteria) -> loop random walk ban jaata hai.
- Latency critical (har iteration 2 calls).
- Ek acche prompt se pehli baar mein kaam ho jaata hai.

## 6. Production pitfalls

- **Self-grading bias**: same model apna kaam zyada achha rate karta hai. Evaluator alag model rakho (`EVAL_MODEL`).
- **Lenient judge**: sab ko 9/10. Prompt mein "be strict, 8+ = genuinely great" + few-shot examples do; judge ko calibrate karo.
- **Vague feedback**: "make it better" useless hai. Evaluator se *specific, actionable* feedback maango.
- **Missing criteria**: judge ne kisi criterion ka score hi nahi diya -> 0 maano (`evaluate()` yahi karta hai), silently pass mat karo.
- **Oscillation**: best-so-far track karo.
- **LLM se counting**: character/hashtag count code se karo, LLM galat ginta hai.

## 7. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Generator with feedback | `evalopt_loop.py` -> `generate(llm, brief, previous)` |
| Hard deterministic checks | `hard_checks()` (length, hashtags) |
| LLM judge with rubric | `evaluate()` -> `llm_json(..., Evaluation)` + `RUBRIC` |
| Strict missing-criterion handling | `evaluate()` -> missing score = 0 |
| 3 stop criteria + best tracking | `optimize()` -> `stop_reason`, `best` |
| Separate models | `main.py` -> `GEN_MODEL`, `EVAL_MODEL` |
