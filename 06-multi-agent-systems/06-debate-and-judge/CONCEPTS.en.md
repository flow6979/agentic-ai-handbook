**Language:** [Hinglish](CONCEPTS.md) · English

# 06 · Debate & Judge: getting to the truth through argument

## The short version

If you take a single answer from one LLM, it can be confidently wrong. Research shows that **accuracy goes up when several agents argue, or when you ask several times and vote**. This project has 4 related patterns:

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
- **Adversarial roles**: each debater has a fixed stance ("never switch sides"). That stops the model from just nodding along with itself, and weak points get exposed.
- **Rounds with memory**: each debater sees the earlier transcript, so rebuttals are possible.
- **Rubric-based judging**: instead of asking "who won?", ask for a score per criterion. That makes the judgement explainable and consistent.
- **Judge ≠ debater**: you have to tell the judge "judge the quality of the arguments, not your own opinion".

## 2. Jury (multiple judges)
A single judge has its own biases: position bias (favours whoever goes first), verbosity bias (favours longer answers), self-preference (favours output from its own model family). **Several judges (ideally from different providers)** + a majority vote dilutes any one judge's bias.
Set `LLM_MODEL_JUDGE1`, `LLM_MODEL_JUDGE2`, `LLM_MODEL_JUDGE3` to different models: that is a real multi-LLM jury.

## 3. Self-consistency
The cheapest form of multi-agent: **one model, N samples**, `temperature=0.8`, then a majority vote over the final answers. It works when answers are short and comparable (math, MCQ, classification). Not for open-ended essays: how would you vote on those?

## 4. Mixture-of-Agents (MoA)
In layer 1, several **proposer** models (ideally from different providers) answer independently. In layer 2 an **aggregator** reads them all, fixes errors and combines the best parts. Different models make different mistakes, so combining them raises quality. (The original MoA paper has multiple layers; here there is 1 proposer layer + 1 aggregator.)

## When to use which

| Pattern | Best for | Cost |
|---|---|---|
| Debate + judge | Decisions with trade-offs, policy questions, "should we X?" | 2×rounds + 1 |
| Jury | High-stakes evaluation, making LLM-as-judge robust | × judges |
| Self-consistency | Math/logic/classification, short answers | × N |
| MoA | Open-ended answer quality, when several providers are available | proposers + 1 |

## Pitfalls
1. **Degenerate agreement**: both debaters agree too quickly. Fix: a fixed stance + "never concede fully".
2. **Judge bias**: position/verbosity bias. Fix: judge again with the order swapped, a word limit, multiple judges.
3. **Cost multiplication**: every pattern means N× calls, so use them only where the value of accuracy > the cost.
4. **Tie handling**: what if the votes are tied? `Counter.most_common` just takes the first one. In production keep an explicit tie-break rule.
5. **Correlated errors**: N samples from the same model make the same mistake. Use different models for diversity.

## How this project uses it

| Concept | File / function |
|---|---|
| Debater roles (fixed stance) | `debate_judge.py` → `debater_prompt(side, motion)` |
| Rounds with history | `debate()` → loop over rounds × sides |
| Rubric + structured verdict | `RUBRIC`, `SideScore`, `Verdict`, `JUDGE_PROMPT` |
| Jury majority | `debate(..., n_judges=3)` → `Counter(votes)` |
| Self-consistency | `self_consistency(question, llm, n)` |
| Mixture-of-agents | `mixture_of_agents(question, proposers, aggregator)` |
| Per-role models | `llm_for("pro"/"con"/"judge1"/"proposer2"/"aggregator")` |
