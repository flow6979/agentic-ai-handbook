**Language:** Hinglish · [English](CONCEPTS.en.md)

# Reflection: agent jo apna kaam khud check karke sudhaarta hai

## 1. Idea

Insaan pehla draft likhte hain, padhte hain, galtiyan dhoondhte hain, phir sudhaarte hain. LLM ka
pehla output bhi aksar "theek-thaak" hota hai, perfect nahi. **Reflection** = model ko apne output
pe feedback dena aur dobara try karwana.

Sabse important sawaal: **feedback kahan se aata hai?**

```
 Feedback source            Pattern                    Is project mein
 ───────────────            ───────                    ───────────────
 Same/doosra LLM (opinion)  Self-Refine / critic loop  reflection_refine.py
 Environment (facts)        Reflexion                  reflection_reflexion.py  (unit tests)
 Human                      Human feedback loop        dekho 11-human-in-the-loop
```

LLM ki raay subjective hai (woh galat bhi approve kar sakta hai). Tests/compiler/validator ka
feedback objective hai. **Jab bhi objective signal mile, woh use karo.**

## 2. Pattern 1: Self-Refine (Generate → Critique → Revise)

```
   Task
    │
    ▼
 ┌──────────┐   draft    ┌──────────────┐
 │GENERATOR │──────────► │   CRITIC     │  llm_json → Critique{score, issues, approved}
 └──────────┘            └──────┬───────┘
      ▲                         │
      │     issues              │ approved / score >= min?
      └─────────────────────────┤ no
                                │ yes
                                ▼
                            Final draft
```

- Critic ka output **structured** hai (`Critique` pydantic model), taaki code decide kar sake ki
  loop rokna hai ya nahi.
- Critic ko task ke **requirements** do, warna woh vague praise dega ("looks great!").
- Generator aur critic alag models bhi ho sakte hain (`critic_llm` param). Alag model ki "aankh" se
  blind spots kam hote hain.

## 3. Pattern 2: Reflexion (environment feedback + lessons memory)

Paper: Shinn et al., 2023. Teen parts:

1. **Actor:** code likhta hai.
2. **Evaluator:** environment. Yahan: unit tests, alag process mein, timeout ke saath.
3. **Self-reflection:** fail hone pe model khud likhta hai "kya galat hua, agli baar kya karna hai".
   Yeh verbal lesson **memory** mein jaata hai aur agle attempt ke prompt mein.

```
            ┌───────────────────────────────────────────┐
            │ Lessons memory (lessons.json)             │
            │ - "normalise input before comparing"      │
            └──────────────┬────────────────────────────┘
                           │ prompt mein inject
                           ▼
   Task ──────────► ┌──────────────┐  code   ┌───────────────────┐
                    │   ACTOR      │────────►│ run_tests()       │
                    │ (write code) │         │ subprocess+timeout│
                    └──────────────┘         └────────┬──────────┘
                           ▲                    PASS? │
                           │                  ┌──yes──┴──no──┐
                           │                  ▼              ▼
                           │               Done      ┌──────────────┐
                           │                         │ REFLECT      │
                           └──── memory.add(lesson) ◄│ "kya galat?" │
                                                     └──────────────┘
```

**Self-refine se difference:** Reflexion ka lesson **generalizable** hota hai aur persist hota
hai. File pe save karo to agle run mein bhi agent pehle se "seekha hua" hota hai (yeh long-term
memory ka simple roop hai, dekho `12-memory`).

## 4. Variants / subtypes

| Variant | Feedback | Note |
|---|---|---|
| Self-Refine | same LLM critic | sabse simple, subjective |
| Critic model (dual LLM) | alag LLM | blind spots kam, cost zyada |
| Reflexion | environment + lessons memory | objective, seekhta hai |
| CRITIC (tool-verified) | critic tools use karta hai (search, calculator) facts check karne | hallucination fix |
| Constitutional / rubric review | fixed principles list | safety, style guides |
| Evaluator-optimizer workflow | fixed loop, alag evaluator | dekho `07-evaluator-optimizer` |
| LATS | reflection + tree search | dekho ToT (`10`) ke saath combine |

## 5. Kab use karein / kab nahi

**Use karo:** quality > latency (code generation, writing, SQL), aur jab clear criteria/tests ho.

**Mat use karo:** simple lookups, low-latency chat, ya jab critic ke paas koi criteria hi nahi
(woh random nitpicks karega, ya har cheez approve karega).

**Cost:** har round = 2 LLM calls (critique + revise). `max_rounds` hamesha rakho.

## 6. Production pitfalls

- **Sycophantic critic:** same model apne output ko approve kar deta hai. Strict rubric do, ya alag model.
- **Over-editing:** har round mein cheezein kharab bhi ho sakti hain. Har round ka score log karo aur
  **best** draft return karo, sirf last nahi (tinker exercise).
- **Sandbox:** LLM ka code **untrusted** hai. `subprocess` asli sandbox nahi: production mein Docker/gVisor/
  Firecracker/E2B, no network, CPU/memory limits.
- **Test leakage:** agar model tests dekh ke hardcode kar de (`if s == 'racecar': return True`)?
  Hidden tests rakho jo model ko nahi dikhte.

## 7. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Structured critique | `reflection_refine.py` → `Critique` |
| Generate → critique → revise loop, stop conditions | `reflection_refine.py` → `self_refine()` |
| Alag critic model support | `self_refine(..., critic_llm=...)` |
| Code runner (subprocess, `-I`, timeout, per-test report) | `reflection_sandbox.py` → `build_harness()`, `run_tests()` |
| Reflexion loop | `reflection_reflexion.py` → `solve_with_reflexion()` |
| Verbal lessons memory, JSON persist | `reflection_reflexion.py` → `LessonMemory` |
| Code extraction from markdown | `reflection_reflexion.py` → `extract_code()` |
