**Language:** Hinglish · [English](CONCEPTS.en.md)

# Prompt Chaining

## 1. Concept kya hai?

Ek bade, mushkil kaam ko ek hi giant prompt mein daalne ki jagah, **chhote sequential steps** mein todo.
Har step ek focused LLM call hai, aur uska output agle step ka input banta hai.
Steps ke beech mein **gates** hote hain: plain code checks jo ensure karte hain ki output theek hai.

```
            ┌──────────┐     ┌──────┐     ┌──────────┐     ┌──────┐     ┌──────────┐
  topic ───►│ OUTLINE  │────►│ GATE │────►│  DRAFT   │────►│ GATE │────►│  POLISH  │───► blog post
            │ (LLM,    │     │(code)│     │ (LLM)    │     │(code)│     │  (LLM)   │
            │  JSON)   │     └──┬───┘     └──────────┘     └──┬───┘     └──────────┘
            └──────────┘        │ fail                        │ fail
                 ▲              │ + feedback                  │ + feedback
                 └──────────────┘            ▲────────────────┘
                     retry (max N)          retry (max N)        N ke baad bhi fail -> STOP (GateError)
```

### Kyun kaam karta hai?
- Har LLM call ka kaam **chhota aur clear** -> accuracy badhti hai (model ek time pe ek cheez sochta hai).
- Beech ke outputs **dikhte hain** -> debugging aasan (kaunsa step bigda?).
- Gates galat output ko **aage failne se rokte hain** (garbage in -> garbage out nahi).
- Har step ke liye alag model/temperature use kar sakte ho.

Trade-off: zyada LLM calls = zyada **latency** (steps sequential hain) aur thoda zyada cost.

## 2. Gates: chaining ki jaan

Gate = deterministic Python check. **LLM se woh cheez check mat karwao jo code kar sakta hai.**

| Gate type | Example | Is project mein |
|---|---|---|
| Schema / format | JSON valid hai? fields hain? | `llm_json` + Pydantic `Outline` |
| Count / length | 3-5 sections, min 40 words | `check_outline`, `check_draft` |
| Consistency | draft mein har outline heading hai? | `check_draft` |
| Uniqueness | duplicate headings nahi | `check_outline` |
| (optional) LLM gate | "kya yeh on-topic hai?" | yahan nahi; zarurat pe add karo |

Gate fail hone par 3 options:
```
 gate fail ──┬──► retry same step, error message as feedback   (yahan: run_step_with_gate)
             ├──► fallback (default value / simpler path)
             └──► stop pipeline, error raise                   (N attempts ke baad)
```

## 3. Subtypes / variants

1. **Linear chain**: A -> B -> C (yeh project).
2. **Chain with gates + retry**: har step ke baad validate, fail pe feedback ke saath retry (yeh project).
3. **Map-reduce chain**: ek step list banata hai, har item pe same step (map), phir combine (reduce).
   Yahan `step_draft` ko per-section call karke map-reduce bana sakte ho (Tinker #2).
4. **Conditional chain**: step ke output pe branch (yeh routing ki taraf jaata hai, 02 dekho).
5. **Multi-model chain**: sasta model outline ke liye, strong model draft ke liye.

## 4. Kab use karein / kab nahi

Use karo jab:
- Kaam natural steps mein toot-ta hai (outline -> draft -> edit, extract -> transform -> summarise).
- Har step ka output check karna possible hai.
- Latency se zyada accuracy important hai.

Mat karo jab:
- Ek hi prompt se achha result aa raha hai (extra calls = waste).
- Steps pehle se pata nahi (tab agent / orchestrator chahiye).
- Real-time, low-latency chahiye (e.g. chat autocomplete).

## 5. Production pitfalls

- **Error compounding**: step 1 ki chhoti galti step 3 tak badi ho jaati hai -> isliye gates.
- **Context loss**: har step ko sirf pichhle ka output milta hai. Zaroori info (tone, audience) explicitly pass karo.
- **Infinite retry**: retry hamesha capped rakho (`max_attempts`).
- **Gate mein LLM**: LLM-based gate bhi galat ho sakta hai; pehle deterministic checks.
- **Observability**: har step ka input/output log karo (`ChainResult.log`), warna pata nahi chalega kaunsa step fail hua.

## 6. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Structured step output | `step_outline()` -> `llm_json(..., Outline)` |
| Free-text steps | `step_draft()`, `step_polish()` -> `llm.complete` |
| Gates | `check_outline()`, `check_draft()` raise `GateError` |
| Retry with feedback | `run_step_with_gate()`: gate ka error message agle prompt mein "previous ... was rejected: ..." |
| Stop on repeated failure | `run_step_with_gate()` N attempts ke baad `GateError` |
| Step log / traceability | `ChainResult.log` |
| Offline demo (gate fail -> retry dikhata hai) | `offline_demo_llm()`: pehla outline duplicate headings wala hai |
