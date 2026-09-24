# 06 · Debate & Judge — Test & Tinker

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
LLM_MODEL_JUDGE1=groq:llama-3.3-70b-versatile LLM_MODEL_JUDGE2=gemini:gemini-2.5-flash \
LLM_MODEL_JUDGE3=openai:gpt-4o-mini python $M debate "Tabs are better than spaces" --judges 3
# self-consistency on a tricky question
python $M consistency "A bat and ball cost 110 rupees. The bat costs 100 more than the ball. Ball price?" --samples 7
# MoA with different proposers
LLM_MODEL_PROPOSER1=groq:llama-3.3-70b-versatile LLM_MODEL_PROPOSER2=gemini:gemini-2.5-flash \
LLM_MODEL_AGGREGATOR=anthropic:claude-sonnet-5 python $M moa "Explain CAP theorem in 3 lines"
```

Expected (offline): debate → `Jury votes: ['pro', 'con', 'pro']`, `WINNER: pro`. consistency → `votes: {'42': 3, '41': 1, '40': 1}`. moa → `Paris (capital of France).`

## Tests

```bash
pytest 06-multi-agent-systems/06-debate-and-judge -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_debate_rounds_alternate_and_judge_scores` | PRO/CON alternate, rubric totals, winner |
| `test_debaters_see_opponent_history` | CON ko PRO ka argument dikhta hai (rebuttal possible) |
| `test_jury_majority_vote` | 3 judges → majority |
| `test_self_consistency_majority` | Majority answer + vote counts |
| `test_mixture_of_agents_uses_all_proposers` | Aggregator ko saare proposer answers milte hain |

## Traces mein kya dekhna hai

`[debate:llm] R2 CON: ...`: kya round 2 mein sach mein PRO ke point ka jawab hai, ya same baat repeat ho rahi hai? Repeat ho rahi hai to prompt mein "address the opponent's LAST point by quoting it" add karo.

## Tinker karo 🔧

1. **Position bias test**: `debate()` mein CON ko pehle bulwao (order swap) aur judge verdicts compare karo.
2. **3-way debate**: ek "neutral pragmatist" debater add karo. Verdict schema update karna padega.
3. **Tie-break**: jury votes tie hon to rubric totals ka average use karo. Implement karo.
4. **Self-consistency with temperature=0**: sab samples same aayenge. Dekho aur samjho ki diversity kyun zaroori hai.
5. **Judge ko debate ke beech bulao**: har round ke baad judge bataye kaun aage hai, aur jo peeche ho usse hint mile.
6. **MoA 2 layers**: aggregator ke output ko phir proposers ko "improve this" ke saath bhejo, phir final aggregate karo.
