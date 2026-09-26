**Language:** Hinglish · [English](CONCEPTS.en.md)

# 06 · Debate & Judge — Behas se sach nikalna

## Seedhi baat

Ek LLM se ek hi jawab lo to woh confident galat bhi ho sakta hai. Research dikhati hai ki **agar kai agents argue karein, ya kai baar poochho aur vote karo, to accuracy badhti hai**. Is project mein 4 related patterns hain:

```
1) DEBATE + JUDGE        2) JURY                3) SELF-CONSISTENCY      4) MIXTURE-OF-AGENTS
PRO ⇄ CON (rounds)       debate transcript      same Q × N (temp>0)      Q → model A ┐
      │                   ├─► judge 1 → pro      → 42, 42, 41, 42, 40         model B ├─► AGGREGATOR → best
      ▼                   ├─► judge 2 → con      → majority = 42              model C ┘
   JUDGE (rubric)         └─► judge 3 → pro
   → winner               → majority = pro
```

## 1. Debate + Judge

```
 motion: "Remote work is better than office work"

 Round 1:  PRO: argument ─────────────►
                        ◄───────────── CON: argument + rebut
 Round 2:  PRO: rebut CON ────────────►
                        ◄───────────── CON: rebut PRO
                      │
                      ▼ full transcript
                ┌───────────┐
                │   JUDGE   │  rubric: evidence, logic, rebuttal (1-10 each)
                └─────┬─────┘
                      ▼
   {"pro": {...}, "con": {...}, "winner": "pro", "reasoning": "..."}
```

Key ideas:
- **Adversarial roles**: har debater ka ek fixed stance hai ("never switch sides"). Isse model apni hi baat pe "haan ji" nahi karta aur weak points expose hote hain.
- **Rounds with memory**: har debater pichhla transcript dekhta hai, isliye rebuttal possible hai.
- **Rubric-based judging**: "kaun jeeta?" poochhne ki jagah criteria-wise score maango. Isse judgement explainable aur consistent hota hai.
- **Judge ≠ debater**: judge ko "argument quality judge karo, apni opinion nahi" bolna zaroori hai.

## 2. Jury (multiple judges)
Ek judge ke apne biases hote hain: position bias (pehle wale ko favour), verbosity bias (lambe jawab ko), self-preference (apne model family ke output ko). **Kai judges (ideally alag providers)** + majority vote se ek ka bias dilute hota hai.
`LLM_MODEL_JUDGE1`, `LLM_MODEL_JUDGE2`, `LLM_MODEL_JUDGE3` alag set karo, yahi asli multi-LLM jury hai.

## 3. Self-consistency
Multi-agent ka sabse sasta roop: **ek hi model, N samples**, `temperature=0.8`, phir final answers ka majority vote. Kaam aata hai jab answer short aur comparable ho (math, MCQ, classification). Open-ended essays pe nahi, kyunki unka vote kaise karoge?

## 4. Mixture-of-Agents (MoA)
Layer 1 mein kai **proposer** models (ideally alag providers) independently answer dete hain. Layer 2 mein ek **aggregator** sab padh ke errors fix karta hai aur best parts mila deta hai. Alag models ki galtiyan alag hoti hain, isliye combine karne se quality badhti hai. (Original MoA paper mein multiple layers hain; yahan 1 proposer layer + 1 aggregator hai.)

## Kab kya use karein

| Pattern | Best for | Cost |
|---|---|---|
| Debate + judge | Decisions with trade-offs, policy questions, "should we X?" | 2×rounds + 1 |
| Jury | High-stakes evaluation, LLM-as-judge ko robust banana | × judges |
| Self-consistency | Math/logic/classification, short answers | × N |
| MoA | Open-ended answer quality, jab kai providers available hon | proposers + 1 |

## Pitfalls
1. **Degenerate agreement**: dono debaters jaldi agree kar lete hain. Fix: fixed stance + "never concede fully".
2. **Judge bias**: position/verbosity bias. Fix: order swap karke dobara judge karo, word limit, multiple judges.
3. **Cost multiplication**: har pattern N× calls hai, isliye sirf wahan use karo jahan accuracy ki value > cost.
4. **Tie handling**: votes barabar hon? `Counter.most_common` pehla le leta hai. Production mein explicit tie-break rule rakho.
5. **Correlated errors**: same model ke N samples same galti karte hain. Diversity ke liye alag models use karo.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Debater roles (fixed stance) | `debate_judge.py` → `debater_prompt(side, motion)` |
| Rounds with history | `debate()` → loop over rounds × sides |
| Rubric + structured verdict | `RUBRIC`, `SideScore`, `Verdict`, `JUDGE_PROMPT` |
| Jury majority | `debate(..., n_judges=3)` → `Counter(votes)` |
| Self-consistency | `self_consistency(question, llm, n)` |
| Mixture-of-agents | `mixture_of_agents(question, proposers, aggregator)` |
| Per-role models | `llm_for("pro"/"con"/"judge1"/"proposer2"/"aggregator")` |
