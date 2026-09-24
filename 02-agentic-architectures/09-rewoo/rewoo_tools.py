"""ReWOO workers (tools). Har tool ek string input leta hai: `tool[input]` syntax ke liye simple."""
from __future__ import annotations

import ast
import operator
import re

from agentkit import tool

# Values sirf numbers hain taaki #E1 seedha calculator mein substitute ho sake.
FACTS = {
    "mount everest height in metres": "8849",
    "eiffel tower height in metres": "330",
    "burj khalifa height in metres": "828",
    "qutub minar height in metres": "73",
    "population of india in millions": "1430",
    "population of japan in millions": "124",
}

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg}


def _arith(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_arith(node.left), _arith(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_arith(node.operand))
    raise ValueError("only + - * / on numbers allowed")


@tool
def lookup(query: str) -> str:
    """Look up a numeric fact, e.g. 'mount everest height in metres'. Returns just the number."""
    words = set(re.findall(r"[a-z]+", query.lower()))
    best = max(FACTS, key=lambda k: len(words & set(k.split())))
    if not words & set(best.split()):
        raise LookupError(f"no fact for {query!r}")
    return FACTS[best]


@tool
def calculator(expression: str) -> str:
    """Evaluate arithmetic like '8849 / 330'."""
    return str(round(_arith(ast.parse(expression, mode="eval").body), 4))


TOOLS = [lookup, calculator]
