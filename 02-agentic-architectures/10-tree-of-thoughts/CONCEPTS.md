# Tree of Thoughts (ToT)

## 1. Chain of Thought ki limit

Chain-of-Thought (CoT) = model step-by-step sochta hai, lekin **ek hi line mein**. Agar pehla step
galat hua, poori chain galat. Wapas jaane (backtrack) ka koi tareeka nahi.

```
CoT:     start ─► step1 ─► step2 ─► step3 ─► answer      (ek raasta, galti = game over)

ToT:                 start
                   /   |   \
               s1a    s1b   s1c        ← kai candidate thoughts (propose)
              / \      |     ✗         ← har ek ko score karo (evaluate), bura = prune
           s2a  s2b   s2c
            ✗    |     \
                24 ✓    ...            ← search: BFS/beam ya DFS + backtrack
```

**ToT** (Yao et al., 2023): problem ko ek **search tree** ki tarah dekho. Har node ek partial solution
(state) hai. LLM do kaam karta hai: naye branches propose karna, aur states ko judge karna. Search
algorithm (classic CS!) decide karta hai kaunsi branch explore karni hai.

## 2. Char components

| Component | Kya hai | Game of 24 mein |
|---|---|---|
| Thought decomposition | ek "thought" kitna bada step hai | do numbers combine karna (`10 - 4 = 6`) |
| Thought generator | LLM har state se k candidates deta hai | `PROPOSE_PROMPT` |
| State evaluator | LLM har state ko value deta hai | `sure=20 / likely=1 / impossible=0.001` |
| Search algorithm | kaise tree explore karein | BFS/beam (`solve_bfs`) ya DFS (`solve_dfs`) |

Plus ek **deterministic validator** (paper mein implicit, production mein zaroori): LLM ki arithmetic
pe bharosa mat karo. `apply_step()` check karta hai ki numbers available hain aur `a op b` sach mein
`result` hai. Galat proposals drop.

## 3. Search algorithms

### BFS / Beam search

```
depth 1:  [9 13 6]=20   [4 13 19]=20   [4 10 4]=20   [..]=0.001 ✗ (beam ke bahar)
             │              │              │
depth 2:  [6 4]=20       [6 22]=0.001   ...          → top-b rakho (beam_width)
             │
depth 3:  [24] ✓
```

Har depth pe saare children banao, score karo, top `beam_width` rakho. Predictable cost, parallel ho
sakta hai, lekin har depth pe bahut LLM calls.

### DFS + pruning + backtracking

```
 start → best child → uska best child → ... dead end? ← backtrack → next child
         (value < threshold wale children kabhi explore nahi = prune)
```

Kam memory, jaldi answer mil sakta hai, lekin bad evaluator = galat gehri branch mein time barbaad.

## 4. Variants / subtypes

- **Self-consistency (CoT-SC):** N independent chains, majority vote. Tree nahi, lekin sabse sasta "multiple paths" idea (dekho `03-parallelization` voting).
- **ToT-BFS / beam** (yeh project), **ToT-DFS** (yeh project).
- **Best-first / A\*:** priority queue by value, globally best state pehle.
- **MCTS / LATS:** Monte Carlo Tree Search + reflection (LATS = Language Agent Tree Search), actions with real tools.
- **Graph of Thoughts (GoT):** thoughts ko merge bhi kar sakte ho (tree nahi, graph).

## 5. Kab use karein / kab nahi

**Use karo:** puzzles, planning, math/constraint problems, creative writing jahan multiple drafts compare
karne ho, jahan **galat early decision costly** ho aur partial states judge ho sakte ho.

**Mat use karo:** simple Q&A, retrieval, chat. **Cost bahut zyada hai**: offline demo mein bhi 48-72 LLM
calls sirf ek puzzle ke liye! Latency bhi.

## 6. Production pitfalls

- **Cost explosion:** `branching^depth`. `beam_width`, `n_propose`, depth sab limit karo; evaluator cache karo (`self._cache`).
- **Evaluator quality:** poora system evaluator jitna hi achha hai. Jahan ho sake deterministic evaluator use karo (terminal state ka check hum khud karte hain, LLM nahi).
- **Duplicate states:** alag raaston se same state aata hai → merge (`State.key()`), warna beam duplicates se bhar jata hai.
- **Temperature:** proposer ko diversity chahiye (`temperature=0.7`), evaluator ko consistency (`0`).

## 7. Is project mein kaise use ho raha hai

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
