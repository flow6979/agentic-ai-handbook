"""Tree of Thoughts (Yao et al., 2023): LLM se sirf ek answer nahi, ek SEARCH TREE.

Char components:
  1. Thought decomposition : ek "thought" = ek step (yahan: do numbers combine karna)
  2. Thought generator     : LLM har state se kai candidate next-steps propose karta hai
  3. State evaluator       : LLM har state ko score karta hai (sure / likely / impossible)
  4. Search algorithm      : BFS/beam (top-b rakho) ya DFS (gehra jao, bura ho to backtrack)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agentkit import LLM, NullTracer, Tracer

from tot_game24 import State, apply_step, is_solved

PROPOSE_PROMPT = """We are playing the Game of 24: combine numbers with + - * / to reach exactly 24.
Numbers left: {numbers}
Propose up to {n} different possible NEXT steps. Each step combines exactly two of the numbers left.
One step per line, in the exact format: a op b = result
Only output the lines."""

VALUE_PROMPT = """Game of 24. Numbers left: {numbers}
Can these numbers reach exactly 24 using + - * / (each number used exactly once)?
Think briefly, then end with ONE word on the last line: sure, likely, or impossible."""

VALUE_MAP = {"sure": 20.0, "likely": 1.0, "impossible": 0.001}  # ToT paper wale values


@dataclass
class ToTResult:
    solved: bool
    steps: list[str]
    llm_calls: int = 0
    states_explored: int = 0
    rejected_proposals: int = 0
    tree: list[list[tuple[str, float]]] = field(default_factory=list)  # har depth pe (state, score)


class TreeOfThoughts:
    def __init__(self, llm: LLM, *, beam_width: int = 3, n_propose: int = 8, tracer: Tracer | None = None):
        self.llm = llm
        self.beam_width = beam_width
        self.n_propose = n_propose
        self.tracer = tracer or NullTracer(name="tot")
        self._cache: dict[tuple, float] = {}

    # --- 2. thought generator -------------------------------------------------
    def propose(self, state: State, result: ToTResult) -> list[State]:
        text = self.llm.complete(PROPOSE_PROMPT.format(numbers=state.show(), n=self.n_propose), temperature=0.7)
        result.llm_calls += 1
        children, seen = [], set()
        for line in text.splitlines():
            child = apply_step(state, line)
            if child is None:
                if line.strip():
                    result.rejected_proposals += 1  # galat arithmetic / non-existent number
                continue
            if child.key() not in seen:  # duplicate states merge karo
                seen.add(child.key())
                children.append(child)
        return children

    # --- 3. state evaluator ---------------------------------------------------
    def evaluate(self, state: State, result: ToTResult) -> float:
        if state.done:  # terminal state: LLM ki zaroorat nahi, deterministic check
            return VALUE_MAP["sure"] if is_solved(state) else 0.0
        if state.key() in self._cache:
            return self._cache[state.key()]
        text = self.llm.complete(VALUE_PROMPT.format(numbers=state.show()))
        result.llm_calls += 1
        words = re.findall(r"[a-z]+", text.lower())
        verdict = next((w for w in reversed(words) if w in VALUE_MAP), "likely")
        value = VALUE_MAP[verdict]
        self._cache[state.key()] = value
        return value

    # --- 4a. BFS / beam search -------------------------------------------------
    def solve_bfs(self, numbers: list[int]) -> ToTResult:
        result = ToTResult(solved=False, steps=[])
        frontier = [State.start(numbers)]
        for depth in range(len(numbers) - 1):
            scored: list[tuple[float, State]] = []
            for st in frontier:
                for child in self.propose(st, result):
                    result.states_explored += 1
                    scored.append((self.evaluate(child, result), child))
            scored.sort(key=lambda x: x[0], reverse=True)
            # Alag parents se same numbers wala state aa sakta hai ([6 4] via do raaste): beam mein ek hi rakho
            unique, seen = [], set()
            for v, s in scored:
                if s.key() not in seen:
                    seen.add(s.key())
                    unique.append((v, s))
            scored = unique
            frontier = [s for _, s in scored[: self.beam_width]]
            result.tree.append([(s.show(), v) for v, s in scored[: self.beam_width]])
            self.tracer.event("info", f"depth {depth + 1}: keep " + ", ".join(f"[{s.show()}]={v:g}" for v, s in scored[: self.beam_width]))
            if not frontier:
                break
        for st in frontier:
            if is_solved(st):
                result.solved, result.steps = True, list(st.history)
                break
        return result

    # --- 4b. DFS with pruning + backtracking ---------------------------------
    def solve_dfs(self, numbers: list[int], prune_below: float = 0.5) -> ToTResult:
        result = ToTResult(solved=False, steps=[])

        def dfs(st: State) -> bool:
            if st.done:
                if is_solved(st):
                    result.steps = list(st.history)
                    return True
                return False
            children = [(self.evaluate(c, result), c) for c in self.propose(st, result)]
            result.states_explored += len(children)
            for value, child in sorted(children, key=lambda x: x[0], reverse=True):
                if value < prune_below:  # "impossible" branch: aage mat jao (prune)
                    continue
                self.tracer.event("info", f"try [{child.show()}] via {child.history[-1]} (v={value:g})")
                if dfs(child):
                    return True
                self.tracer.event("error", f"backtrack from [{child.show()}]")
            return False

        result.solved = dfs(State.start(numbers))
        return result
