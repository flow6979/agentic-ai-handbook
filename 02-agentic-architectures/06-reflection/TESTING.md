**Language:** Hinglish · [English](TESTING.en.md)

# 06-reflection: Testing aur tinkering

## Setup
Repo root se `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.

## 1. Offline demos

```bash
python 02-agentic-architectures/06-reflection/main.py refine --offline
python 02-agentic-architectures/06-reflection/main.py reflexion --offline
```

Dekho:
- **refine:** round 1 score 4 aur issues (price missing...), round 2 score 9, approved.
- **reflexion:** attempt 1 mein `FAIL: ... Panama` (asli subprocess mein tests chale!), phir `LESSON:`,
  attempt 2 PASS.

## 2. Real LLM

```bash
python 02-agentic-architectures/06-reflection/main.py refine "Write a tweet (max 200 chars) announcing a Hindi coding bootcamp. Must include date 12 Oct, a price, and 2 hashtags."
python 02-agentic-architectures/06-reflection/main.py reflexion --lessons /tmp/lessons.json
```

Reflexion ko do baar chalao same `--lessons` file ke saath. Doosri baar prompt mein pichle lessons
jaate hain. `cat /tmp/lessons.json` karke dekho model ne kya seekha.

Strong models aksar palindrome pehli baar mein solve kar lete hain. Reflexion dekhna ho to task
mushkil karo (neeche exercise 2).

## 3. Offline tests

```bash
pytest 02-agentic-architectures/06-reflection -v
```

Cover: sandbox (pass/fail/timeout/syntax error), code extraction, refine loop (issues revise prompt mein
jaate hain), max_rounds, Reflexion (lesson agle prompt mein + file mein persist).

## 4. Tinker karo

1. **Best-of-rounds:** `self_refine` sirf last draft return karta hai. Har round ka score track karke
   highest score wala draft return karo.
2. **Mushkil coding task:** `CODE_TASK` ko "roman numeral to int with validation (raise ValueError on 'IIII')"
   banao aur tricky tests do. Kitne attempts lagte hain? Lessons kaise hain?
3. **Hidden tests:** model ko sirf 2 tests dikhao, `run_tests` mein 4 chalao. Kya model overfit karta hai?
4. **Dual model critic:** `self_refine(llm, task, critic_llm=get_llm("<doosra provider>"))`. Kya critic zyada strict hai?
5. **Tool-verified critic (CRITIC pattern):** critic ko `04-react` jaisa lookup/calculator tool do taaki woh facts verify kare.
6. **Timeout dekho:** offline script mein pehle attempt ka code `while True: pass` karo. `TIMEOUT` observation aata hai aur reflection mein jaata hai.
