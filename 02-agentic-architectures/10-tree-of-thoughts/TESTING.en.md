**Language:** [Hinglish](TESTING.md) · English

# 10-tree-of-thoughts: Testing and tinkering

## Setup
From the repo root: `pip install -e ".[all]"`, and put `LLM_MODEL` + a key in `.env`.

## 1. Offline demo

```bash
python 02-agentic-architectures/10-tree-of-thoughts/main.py --offline
python 02-agentic-architectures/10-tree-of-thoughts/main.py --offline --search dfs
```

The offline "LLM" proposes/evaluates by brute force (to show the search mechanics). Look for:
- `depth N beam:` → which states survived at each level, and their values.
- `rejected_invalid_proposals` → the validator dropped wrong lines from the fake LLM such as `a + b = 999`.
- `llm_calls`: compare BFS vs DFS.
- In DFS mode, `AGENT_VERBOSE=1` shows the `try [...]` / `backtrack from [...]` lines.

## 2. Real LLM

```bash
python 02-agentic-architectures/10-tree-of-thoughts/main.py 4 9 10 13
python 02-agentic-architectures/10-tree-of-thoughts/main.py 1 5 5 5 --beam 5        # hard: 5*(5-1/5)
python 02-agentic-architectures/10-tree-of-thoughts/main.py 3 3 8 8 --search dfs    # 8/(3-8/3)
```

Look at: how many wrong proposals the real model makes (`rejected_invalid_proposals`), how accurate the evaluator is,
and what difference a wider beam makes on hard puzzles (the ones with fractions). **Cost warning:** one run =
dozens of LLM calls. Use a cheap model (`groq:llama-3.1-8b-instant`) or local ollama.

## 3. Offline tests

```bash
pytest 02-agentic-architectures/10-tree-of-thoughts -v
```

Covered: the validator (wrong arithmetic, missing number, fractions), solvable brute force, BFS solve + replay
check, DFS prune+solve, unsolvable input, evaluator last-word parsing + caching.

## 4. Tinker with it

1. **CoT baseline:** try 10 puzzles with a single prompt "solve 24 for 4 9 10 13, show steps" and
   verify them with `apply_step`. Compare the success rate with ToT.
2. **Self-consistency:** run CoT 5 times and take the answer that passes the validator. Cost vs ToT?
3. **Best-first search:** write a solver with a priority queue using `heapq` (expand the globally best state first).
4. **Cheap evaluator:** give the evaluator a separate small model and the proposer a big one. Look at accuracy and cost.
5. **Beam width sweep:** 10 puzzles at `--beam 1` (greedy) vs 3 vs 5. Graph: beam vs success vs llm_calls.
6. **New problem:** apply this framework to another puzzle (e.g. a word ladder: COLD → WARM) by changing only `State`,
   `apply_step` and the prompts.
