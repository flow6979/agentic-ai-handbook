"""ReAct demo ke tools: ek safe calculator aur ek chhota local knowledge base.

Dono ReAct styles (text loop aur native function calling) yahi tools use karte hain,
taaki comparison fair ho.
"""
from __future__ import annotations

import ast
import operator
import re

from agentkit import tool

# Chhota "encyclopedia". Real project mein yeh web search / DB / RAG hota.
KB = {
    "eiffel tower height": "The Eiffel Tower is 330 metres tall.",
    "mount everest height": "Mount Everest is 8849 metres tall.",
    "burj khalifa height": "The Burj Khalifa is 828 metres tall.",
    "speed of light": "Light travels at about 299792 km per second.",
    "population of india": "India has about 1.43 billion people (2023).",
    "capital of australia": "The capital of Australia is Canberra.",
}

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Sirf arithmetic allow karo. `eval()` kabhi mat use karo: LLM ka output untrusted input hai."""

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"unsupported expression element: {ast.dump(node)[:60]}")

    return ev(ast.parse(expression, mode="eval").body)


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression like '8849 / 330'. Supports + - * / ** % and parentheses."""
    value = safe_eval(expression)
    return str(round(value, 6))


@tool
def lookup(query: str) -> str:
    """Look up a fact in the local knowledge base, e.g. 'mount everest height'."""
    words = set(re.findall(r"[a-z]+", query.lower()))
    best_key, best_score = None, 0
    for key in KB:
        score = len(words & set(key.split()))
        if score > best_score:
            best_key, best_score = key, score
    if best_key is None:
        return f"No entry found for {query!r}. Known topics: {', '.join(KB)}"
    return KB[best_key]


TOOLS = [calculator, lookup]
