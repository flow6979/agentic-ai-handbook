**Language:** [Hinglish](TESTING.md) · English

# 09-rewoo: Testing and tinkering

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + a key in `.env`.

## 1. Offline demo

```bash
python 02-agentic-architectures/09-rewoo/main.py --offline
```

Look for:
- `parallel levels: [['#E1', '#E2', '#E3'], ['#E4'], ['#E5']]` → the three lookups ran in parallel.
- `ReWOO -> llm_calls=2` vs `ReAct -> llm_calls=6`, and the difference in input tokens (~3x).

## 2. Real LLM

```bash
python 02-agentic-architectures/09-rewoo/main.py --compare "How many times taller is Burj Khalifa than Qutub Minar?"
python 02-agentic-architectures/09-rewoo/main.py --compare "Population of India divided by population of Japan, in millions?"
```

What to check:
- Did the model follow the format correctly (`#E1 = lookup[...]`)? If not, you'll see the error message from `parse_plan`.
- In `--compare`, compare the `input_tokens` (real provider usage) of both.
- Do both give the same answer?

## 3. Offline tests

```bash
pytest 02-agentic-architectures/09-rewoo -v
```

Covered: plan parsing + dependency levels, bad plan rejection (unknown tool, forward reference, empty),
only 2 LLM calls end to end, a worker error becomes evidence, the `LLM[...]` worker + substitution.

## 4. Tinker with it

1. **Failure case:** ask "Height of Taj Mahal divided by Qutub Minar?" (there's no Taj data). The evidence
   will contain an ERROR. What does the solver say? Now build a hybrid: if any evidence is an ERROR, run an Agent like `04-react`.
2. **Parallel vs sequential time:** put `time.sleep(1)` in `lookup`. Measure the time of `ReWOO(..., parallel=False)` vs `True`.
3. **Few-shot planner:** put an example plan in `PLANNER_PROMPT`. Do parse errors drop on a small model (`ollama:llama3.2`)?
4. **LLM worker:** change a value in `FACTS` to "8849 metres". The plan will fail (calculator). Teach the planner
   to use an `LLM[Extract only the number from #E1]` step.
5. **Scale test:** ask a question that needs 8 facts. Plot ReAct vs ReWOO tokens (steps vs tokens).
