**Language:** [Hinglish](TESTING.md) · English

# 06 · Debate & Judge: Test & Tinker

## Run

```bash
M=06-multi-agent-systems/06-debate-and-judge/main.py

# offline
python $M debate "Remote work is better than office work" --judges 3 --offline
python $M consistency "What is 6 times 7?" --offline
python $M moa "What is the capital of France?" --offline

# real LLM
python $M debate "AI will create more jobs than it destroys" --rounds 3
# multi-provider jury
LLM_MODEL_JUDGE1=groq:llama-3.3-70b-versatile LLM_MODEL_JUDGE2=gemini:gemini-3.8-flash \
LLM_MODEL_JUDGE3=openai:gpt-4o-mini python $M debate "Tabs are better than spaces" --judges 3
# self-consistency on a tricky question
python $M consistency "A bat and ball cost 110 rupees. The bat costs 100 more than the ball. Ball price?" --samples 7
# MoA with different proposers
LLM_MODEL_PROPOSER1=groq:llama-3.3-70b-versatile LLM_MODEL_PROPOSER2=gemini:gemini-3.8-flash \
LLM_MODEL_AGGREGATOR=anthropic:claude-sonnet-5 python $M moa "Explain CAP theorem in 3 lines"
```

Expected (offline): debate → `Jury votes: ['pro', 'con', 'pro']`, `WINNER: pro`. consistency → `votes: {'42': 3, '41': 1, '40': 1}`. moa → `Paris (capital of France).`

## Tests

```bash
pytest 06-multi-agent-systems/06-debate-and-judge -v
```

| Test | What it proves |
|---|---|
| `test_debate_rounds_alternate_and_judge_scores` | PRO/CON alternate, rubric totals, winner |
| `test_debaters_see_opponent_history` | CON sees PRO's argument (so rebuttal is possible) |
| `test_jury_majority_vote` | 3 judges → majority |
| `test_self_consistency_majority` | Majority answer + vote counts |
| `test_mixture_of_agents_uses_all_proposers` | The aggregator receives every proposer's answer |

## What to look for in traces

`[debate:llm] R2 CON: ...`: does round 2 actually answer PRO's point, or is it repeating the same thing? If it repeats, add "address the opponent's LAST point by quoting it" to the prompt.

## Tinker 🔧

1. **Position bias test**: have CON go first in `debate()` (swap the order) and compare the judge verdicts.
2. **3-way debate**: add a "neutral pragmatist" debater. You will need to update the Verdict schema.
3. **Tie-break**: if the jury votes are tied, use the average of the rubric totals. Implement it.
4. **Self-consistency with temperature=0**: every sample will come back the same. Watch this and understand why diversity matters.
5. **Call the judge mid-debate**: after every round the judge says who is ahead, and whoever is behind gets a hint.
6. **MoA with 2 layers**: send the aggregator's output back to the proposers with "improve this", then aggregate a final time.
