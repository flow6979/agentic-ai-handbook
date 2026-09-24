"""Ek chhoti team: manager + 2 specialists (math expert, copywriter).

    Manager (tools: ask_math_expert, ask_copywriter)
      ├── MathExpert agent  (tools: calculate, percent_change)
      └── Copywriter agent  (no tools, JSON output: {headline, body})
"""
from __future__ import annotations

import ast
import operator

from agentkit import LLM, Agent, NullTracer, Tracer, tool

from agent_as_tool import agent_as_tool

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    # eval() kabhi mat use karo LLM input pe; sirf arithmetic allow karo
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only arithmetic is allowed")


@tool
def calculate(expression: str) -> float:
    """Evaluate an arithmetic expression like '(1200-950)/950*100'."""
    return round(_safe_eval(ast.parse(expression, mode="eval").body), 4)


@tool
def percent_change(old: float, new: float) -> float:
    """Percent change from old to new value."""
    return round((new - old) / old * 100, 2)


def build_team(manager_llm: LLM, math_llm: LLM, writer_llm: LLM, verbose: bool = True) -> Agent:
    tr = (lambda n: Tracer(name=n)) if verbose else (lambda n: NullTracer(n))
    math_expert = Agent(
        math_llm, [calculate, percent_change],
        "You are a careful math expert. Always use tools for arithmetic. Reply with the number and one line of reasoning.",
        name="math_expert", max_steps=6, tracer=tr("math_expert"),
    )
    copywriter = Agent(
        writer_llm, [],
        'You write short marketing copy. Reply ONLY as JSON: {"headline": str, "body": str}.',
        name="copywriter", max_steps=2, tracer=tr("copywriter"),
    )
    return Agent(
        manager_llm,
        [
            agent_as_tool(math_expert, "ask_math_expert", "Delegate any calculation to a math specialist."),
            agent_as_tool(copywriter, "ask_copywriter", "Delegate writing marketing copy. Returns {headline, body}.", expect_json=True),
        ],
        "You are a manager. Break the user's request into sub-tasks and delegate to specialists. "
        "Specialists do NOT see this conversation, so each task must be self-contained. Then combine results.",
        name="manager", max_steps=8, tracer=tr("manager"),
    )
