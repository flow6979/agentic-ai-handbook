**Language:** Hinglish · [English](TESTING.en.md)

# 05-plan-and-execute: Testing aur tinkering

## Setup
Repo root se: `pip install -e ".[all]"`, aur `.env` mein `LLM_MODEL` + key.

## 1. Offline demo

```bash
python 02-agentic-architectures/05-plan-and-execute/main.py --offline
```

Output mein dekho:
- `=== Plans ===` → `v0` (Kasol wala) aur `v1` (Jaipur wala). Replanning ka proof.
- `✗ Find flights from Delhi to Kasol` → tool ne `LookupError` diya, executor ne `FAILED:` bola.
- Trace (stderr) mein `REPLANNER: replan (...)` line.

## 2. Real LLM

```bash
python 02-agentic-architectures/05-plan-and-execute/main.py "Plan a 2-night trip from Delhi to Goa. Check weather, cheapest flight, a hotel, and total cost."
python 02-agentic-architectures/05-plan-and-execute/main.py "Weekend trip from Delhi to Manali with total cost"
```

Doosre wale mein `search_flights(Delhi, Manali)` fail hoga (data nahi hai). Dekho real model kaise
replan karta hai: kya woh user se poochhe bina city badal deta hai? Kya woh sahi hai?

Kya check karna hai:
- Planner ne kitne steps banaye? Kya woh tools se match karte hain?
- Executor ek step mein ek hi kaam kar raha hai ya aage bhag raha hai?
- Replanner `finish` sahi time pe bolta hai?

## 3. Offline tests

```bash
pytest 02-agentic-architectures/05-plan-and-execute -v
```

Cover: tools (safe calculator), happy path (continue → finish), failure → replan, replan budget (infinite replan loop ruk jata hai).

## 4. Tinker karo

1. **Model mixing:** `PlanAndExecute` mein `planner_llm` aur `executor_llm` alag karo. Planner ke liye
   `get_llm("anthropic:...")`, executor ke liye `get_llm("groq:llama-3.1-8b-instant")`. Quality aur cost compare karo.
2. **Replan only on failure:** `run()` mein replanner tabhi call karo jab `rec.failed` ho ya steps khatam hon.
   Kitne LLM calls bache? Kya quality giri?
3. **Structured step result:** `FAILED:` string ki jagah executor se `llm_json` ke through
   `{status: "ok"|"failed", result: str}` lo.
4. **Human approval of plan:** `plan()` ke baad plan print karo aur `input("approve? ")` se confirm lo.
   Reject pe user feedback ke saath dobara plan banao.
5. **Parallel steps (LLMCompiler idea):** planner se `depends_on: list[int]` bhi lo aur independent steps
   `concurrent.futures.ThreadPoolExecutor` mein parallel chalao.
