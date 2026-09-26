**Language:** Hinglish · [English](TESTING.en.md)

# 10-tree-of-thoughts: Testing aur tinkering

## Setup
Repo root se `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.

## 1. Offline demo

```bash
python 02-agentic-architectures/10-tree-of-thoughts/main.py --offline
python 02-agentic-architectures/10-tree-of-thoughts/main.py --offline --search dfs
```

Offline "LLM" brute force se propose/evaluate karta hai (search mechanics dikhane ke liye). Dekho:
- `depth N beam:` → har level pe kaunse states bache aur unki value.
- `rejected_invalid_proposals` → fake LLM ki `a + b = 999` jaisi galat lines validator ne drop ki.
- `llm_calls`: BFS vs DFS compare karo.
- DFS mode mein `AGENT_VERBOSE=1` se `try [...]` / `backtrack from [...]` lines.

## 2. Real LLM

```bash
python 02-agentic-architectures/10-tree-of-thoughts/main.py 4 9 10 13
python 02-agentic-architectures/10-tree-of-thoughts/main.py 1 5 5 5 --beam 5        # mushkil: 5*(5-1/5)
python 02-agentic-architectures/10-tree-of-thoughts/main.py 3 3 8 8 --search dfs    # 8/(3-8/3)
```

Dekho: real model kitne galat proposals deta hai (`rejected_invalid_proposals`), evaluator kitna sahi hai,
aur mushkil puzzles (fractions wale) mein beam badhane se kya farq padta hai. **Cost warning:** ek run =
dozens of LLM calls. Sasta model (`groq:llama-3.1-8b-instant`) ya local ollama use karo.

## 3. Offline tests

```bash
pytest 02-agentic-architectures/10-tree-of-thoughts -v
```

Cover: validator (galat arithmetic, missing number, fractions), solvable brute force, BFS solve + replay
check, DFS prune+solve, unsolvable input, evaluator last-word parsing + caching.

## 4. Tinker karo

1. **CoT baseline:** ek single prompt "solve 24 for 4 9 10 13, show steps" se 10 puzzles try karo aur
   `apply_step` se verify karo. ToT ka success rate compare karo.
2. **Self-consistency:** CoT ko 5 baar chalao aur jo answer validator pass kare woh lo. Cost vs ToT?
3. **Best-first search:** `heapq` se priority queue wala solver likho (global best state pehle expand).
4. **Cheap evaluator:** evaluator ke liye alag chhota model do, proposer ke liye bada. Accuracy aur cost dekho.
5. **Beam width sweep:** `--beam 1` (greedy) vs 3 vs 5 pe 10 puzzles. Graph: beam vs success vs llm_calls.
6. **Naya problem:** is framework ko ek aur puzzle pe lagao (e.g. word ladder: COLD → WARM), sirf `State`,
   `apply_step`, aur prompts badal ke.
