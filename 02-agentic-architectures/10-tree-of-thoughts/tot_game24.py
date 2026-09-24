"""Game of 24: environment + deterministic checker.

4 numbers do, +, -, *, / se 24 banao (har number ek baar). Example: 4 9 10 13 →
(10 - 4) * (13 - 9) = 24.

ToT ke liye yeh perfect toy problem hai: har step (do numbers combine karna) ek "thought" hai,
galat early choice se aage solution impossible ho jata hai (isliye backtracking/search chahiye),
aur final answer deterministic check ho sakta hai.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

_STEP = re.compile(r"(-?\d+(?:/\d+)?(?:\.\d+)?)\s*([+\-*/x×])\s*(-?\d+(?:/\d+)?(?:\.\d+)?)\s*=\s*(-?\d+(?:/\d+)?(?:\.\d+)?)")


def fmt(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _num(s: str) -> Fraction:
    return Fraction(s)  # "3", "3/4", "0.75" sab chalte hain


@dataclass(frozen=True)
class State:
    numbers: tuple[Fraction, ...]
    history: tuple[str, ...] = ()

    @staticmethod
    def start(nums: list[int]) -> "State":
        return State(tuple(Fraction(n) for n in nums))

    def key(self) -> tuple:
        return tuple(sorted(self.numbers))

    def show(self) -> str:
        return " ".join(fmt(n) for n in self.numbers)

    @property
    def done(self) -> bool:
        return len(self.numbers) == 1


def compute(a: Fraction, op: str, b: Fraction) -> Fraction | None:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op in "*x×":
        return a * b
    if op == "/":
        return a / b if b != 0 else None
    return None


def apply_step(state: State, line: str) -> State | None:
    """Model ka proposed step ('10 - 4 = 6') validate karke naya state do. Galat step → None.

    Yeh deterministic VALIDATOR hai: LLM ki arithmetic pe bharosa nahi, hum khud check karte hain.
    """
    m = _STEP.search(line)
    if not m:
        return None
    a, op, b, claimed = _num(m.group(1)), m.group(2), _num(m.group(3)), _num(m.group(4))
    remaining = list(state.numbers)
    for x in (a, b):
        if x not in remaining:
            return None  # model ne aisa number use kiya jo bacha hi nahi
        remaining.remove(x)
    result = compute(a, op, b)
    if result is None or result != claimed:
        return None  # arithmetic galat
    op_norm = "*" if op in "x×" else op
    return State(tuple(remaining + [result]), state.history + (f"{fmt(a)} {op_norm} {fmt(b)} = {fmt(result)}",))


def is_solved(state: State) -> bool:
    return state.done and state.numbers[0] == 24


def all_next_steps(state: State) -> list[str]:
    """Saare valid next steps (brute force). Offline fake LLM aur tests ke liye."""
    out = []
    nums = state.numbers
    for i, j in combinations(range(len(nums)), 2):
        a, b = nums[i], nums[j]
        for x, y in ((a, b), (b, a)):
            for op in "+-*/":
                r = compute(x, op, y)
                if r is not None and r >= 0:
                    out.append(f"{fmt(x)} {op} {fmt(y)} = {fmt(r)}")
    return list(dict.fromkeys(out))


def solvable(numbers: tuple[Fraction, ...]) -> bool:
    if len(numbers) == 1:
        return numbers[0] == 24
    st = State(numbers)
    return any(solvable(apply_step(st, s).numbers) for s in all_next_steps(st))
