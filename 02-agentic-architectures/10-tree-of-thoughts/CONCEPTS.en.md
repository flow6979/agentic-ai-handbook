**Language:** [Hinglish](CONCEPTS.md) · English

# Tree of Thoughts (ToT)

## 1. The limit of Chain of Thought

Chain-of-Thought (CoT) = the model thinks step by step, but **along a single line**. If the first step
is wrong, the whole chain is wrong. There is no way to go back (backtrack).

```
CoT:     start ─► step1 ─► step2 ─► step3 ─► answer      (one path, a mistake = game over)

ToT:                 start
                   /   |   \
               s1a    s1b   s1c        ← several candidate thoughts (propose)
              / \      |     ✗         ← score each one (evaluate), bad = prune
           s2a  s2b   s2c
            ✗    |     \
                24 ✓    ...            ← search: BFS/beam or DFS + backtrack
```

**ToT** (Yao et al., 2023): treat the problem as a **search tree**. Each node is a partial solution
(state). The LLM does two jobs: proposing new branches, and judging states. A search
algorithm (classic CS!) decides which branch to explore.

## 2. Four components

| Component | What it is | In Game of 24 |
|---|---|---|
| Thought decomposition | how big a step one "thought" is | combining two numbers (`10 - 4 = 6`) |
| Thought generator | the LLM gives k candidates from each state | `PROPOSE_PROMPT` |
| State evaluator | the LLM assigns a value to each state | `sure=20 / likely=1 / impossible=0.001` |
| Search algorithm | how to explore the tree | BFS/beam (`solve_bfs`) or DFS (`solve_dfs`) |

Plus a **deterministic validator** (implicit in the paper, essential in production): don't trust the LLM's
arithmetic. `apply_step()` checks that the numbers are available and that `a op b` really equals
`result`. Wrong proposals are dropped.

## 3. Search algorithms

### BFS / Beam search

```
depth 1:  [9 13 6]=20   [4 13 19]=20   [4 10 4]=20   [..]=0.001 ✗ (outside the beam)
             │              │              │
depth 2:  [6 4]=20       [6 22]=0.001   ...          → keep the top-b (beam_width)
             │
depth 3:  [24] ✓
```

At each depth, generate all children, score them, keep the top `beam_width`. Predictable cost, can be
parallelised, but many LLM calls at every depth.

### DFS + pruning + backtracking

```
 start → best child → its best child → ... dead end? ← backtrack → next child
         (children with value < threshold are never explored = prune)
```

Less memory and it can find an answer quickly, but a bad evaluator = time wasted deep in a wrong branch.

## 4. Variants / subtypes

- **Self-consistency (CoT-SC):** N independent chains, majority vote. Not a tree, but the cheapest "multiple paths" idea (see the voting in `03-parallelization`).
- **ToT-BFS / beam** (this project), **ToT-DFS** (this project).
- **Best-first / A\*:** a priority queue by value, the globally best state first.
- **MCTS / LATS:** Monte Carlo Tree Search + reflection (LATS = Language Agent Tree Search), with actions using real tools.
- **Graph of Thoughts (GoT):** thoughts can also be merged (a graph, not a tree).

## 5. When to use it / when not to

**Use it for:** puzzles, planning, math/constraint problems, creative writing where multiple drafts need comparing,
anywhere a **wrong early decision is costly** and partial states can be judged.

**Don't use it for:** simple Q&A, retrieval, chat. **The cost is very high**: even the offline demo makes 48-72 LLM
calls for a single puzzle! Latency too.

## 6. Production pitfalls

- **Cost explosion:** `branching^depth`. Limit `beam_width`, `n_propose` and depth; cache the evaluator (`self._cache`).
- **Evaluator quality:** the whole system is only as good as the evaluator. Use a deterministic evaluator wherever possible (we check terminal states ourselves, not the LLM).
- **Duplicate states:** the same state arrives by different paths → merge (`State.key()`), otherwise the beam fills up with duplicates.
- **Temperature:** the proposer needs diversity (`temperature=0.7`), the evaluator needs consistency (`0`).

## 7. How this project uses it

| Concept | File / function |
|---|---|
| State (numbers + history), exact math with `Fraction` | `tot_game24.py` → `State`, `fmt` |
| Deterministic validator | `tot_game24.py` → `apply_step()` |
| Final check | `tot_game24.py` → `is_solved()` |
| Brute force (offline fake LLM + tests) | `all_next_steps()`, `solvable()` |
| Thought generator | `tot_search.py` → `TreeOfThoughts.propose()` |
| State evaluator + cache + value map | `TreeOfThoughts.evaluate()`, `VALUE_MAP` |
| BFS/beam + global dedupe | `TreeOfThoughts.solve_bfs()` |
| DFS + pruning + backtracking | `TreeOfThoughts.solve_dfs()` |
