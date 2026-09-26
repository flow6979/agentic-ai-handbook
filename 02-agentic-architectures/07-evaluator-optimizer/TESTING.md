**Language:** Hinglish · [English](TESTING.en.md)

# Testing: evaluator-optimizer (launch tweet polisher)

## Setup
Repo root: `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.
Better results ke liye generator aur judge alag:
```
GEN_MODEL=groq:llama-3.3-70b-versatile
EVAL_MODEL=gemini:gemini-2.5-flash
```

## Run

```bash
python 02-agentic-architectures/07-evaluator-optimizer/main.py --offline
python 02-agentic-architectures/07-evaluator-optimizer/main.py
python 02-agentic-architectures/07-evaluator-optimizer/main.py "Chai Point - office chai delivery in 10 min, Bangalore" --threshold 9
```

## Kya dekhna hai

```
--- iteration 1 ---
Snapdeploy is a new tool ... #devops #cloud #startup
hard_errors=['too long: 359 chars > 280', 'more than 2 hashtags'] scores={...0...}   <- judge call hua hi nahi

--- iteration 2 ---
hard_errors=[] scores={'clarity': 7, 'hook': 3, 'cta': 2}
feedback='Weak hook, no CTA. Lead with the pain.'                                    <- specific feedback

--- iteration 3 ---
Stop babysitting deploys. ...
scores={'clarity': 9, 'hook': 8, 'cta': 8}
STOP: passed
```

- Real LLM pe dekho: kya feedback ke baad sach mein score badhta hai? Kitne iterations lagte hain?
- `STOP: no_improvement` aaye to dekho BEST kaunsa iteration tha (aksar last nahi hota).

## Offline tests

```bash
pytest 02-agentic-architectures/07-evaluator-optimizer -v
```
- `test_loop_passes_on_third_iteration`: hard-fail draft judge tak nahi gaya (`len(ev.calls) == 2`), feedback agle prompt mein gaya.
- `test_stops_on_no_improvement_and_keeps_best`: scores gir rahe the -> ruk gaya, best = v1.
- `test_missing_criterion_counts_as_zero`: judge ne `cta` skip kiya -> 0, pass nahi hua.

## Tinker karo

1. **Self-grading bias**: `GEN_MODEL` aur `EVAL_MODEL` same rakho vs alag. Average iterations aur final scores compare karo.
2. **Naya criterion**: `RUBRIC` mein `"tone": "Is it confident but not hypey?"` add karo. Pass karna mushkil hua?
3. **Execution-based evaluator**: naya project: generator Python function likhe, evaluator `pytest` chalaye (subprocess), failures feedback banein. Yeh coding agents ka core loop hai.
4. **Judge calibration**: judge ko 5 known-good aur 5 known-bad tweets do (few-shot) system prompt mein. Scores ka spread badla?
5. **Threshold vs cost**: `--threshold 6/8/10` pe iterations + tokens note karo. Kahan diminishing returns shuru hote hain?
