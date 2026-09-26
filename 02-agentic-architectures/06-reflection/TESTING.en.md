**Language:** [Hinglish](TESTING.md) · English

# 06-reflection: Testing and tinkering

## Setup
From the repo root: `pip install -e ".[all]"`, put `LLM_MODEL` + key in `.env`.

## 1. Offline demos

```bash
python 02-agentic-architectures/06-reflection/main.py refine --offline
python 02-agentic-architectures/06-reflection/main.py reflexion --offline
```

Look for:
- **refine:** round 1 score 4 with issues (price missing...), round 2 score 9, approved.
- **reflexion:** `FAIL: ... Panama` in attempt 1 (the tests ran in a real subprocess!), then `LESSON:`,
  attempt 2 PASS.

## 2. Real LLM

```bash
python 02-agentic-architectures/06-reflection/main.py refine "Write a tweet (max 200 chars) announcing a Hindi coding bootcamp. Must include date 12 Oct, a price, and 2 hashtags."
python 02-agentic-architectures/06-reflection/main.py reflexion --lessons /tmp/lessons.json
```

Run Reflexion twice with the same `--lessons` file. The second time, the previous lessons go into the
prompt. Run `cat /tmp/lessons.json` to see what the model learned.

Strong models often solve the palindrome on the first try. To see Reflexion in action, make the task
harder (exercise 2 below).

## 3. Offline tests

```bash
pytest 02-agentic-architectures/06-reflection -v
```

Covers: sandbox (pass/fail/timeout/syntax error), code extraction, the refine loop (issues go into the revise
prompt), max_rounds, Reflexion (the lesson goes into the next prompt + persists to a file).

## 4. Tinker with it

1. **Best-of-rounds:** `self_refine` returns only the last draft. Track each round's score and
   return the draft with the highest score.
2. **A harder coding task:** change `CODE_TASK` to "roman numeral to int with validation (raise ValueError on 'IIII')"
   and give tricky tests. How many attempts does it take? What do the lessons look like?
3. **Hidden tests:** show the model only 2 tests, but run 4 in `run_tests`. Does the model overfit?
4. **Dual model critic:** `self_refine(llm, task, critic_llm=get_llm("<another provider>"))`. Is the critic stricter?
5. **Tool-verified critic (the CRITIC pattern):** give the critic a lookup/calculator tool like in `04-react` so it can verify facts.
6. **See the timeout:** in the offline script, make the first attempt's code `while True: pass`. A `TIMEOUT` observation appears and goes into the reflection.
