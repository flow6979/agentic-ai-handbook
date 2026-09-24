"""Doosra chhota MCP server (multi-server demo ke liye): calculator + time + unit conversion.

    python mcp_utils_server.py     # stdio
"""
from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod}

_UNITS = {("km", "mi"): 0.621371, ("mi", "km"): 1.609344, ("kg", "lb"): 2.204623, ("lb", "kg"): 0.453592}


def _safe_eval(expr: str) -> float:
    """eval() kabhi mat use karo tool mein! Sirf arithmetic AST allow karo."""
    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ToolError(f"unsupported expression: {ast.dump(node)[:60]}")
    return ev(ast.parse(expr, mode="eval").body)


def build_utils_server() -> MCPServer:
    mcp = MCPServer("utils", version="1.0.0", instructions="Math, time and unit conversion helpers.")

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    def calculate(expression: str) -> str:
        """Evaluate an arithmetic expression like '(2+3)*4'."""
        try:
            return str(_safe_eval(expression))
        except (SyntaxError, ZeroDivisionError) as e:
            raise ToolError(str(e)) from e

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    def utc_now() -> str:
        """Current UTC date-time in ISO format."""
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    def convert_units(value: float, from_unit: str, to_unit: str) -> str:
        """Convert between km/mi and kg/lb."""
        factor = _UNITS.get((from_unit.lower(), to_unit.lower()))
        if factor is None:
            raise ToolError(f"unsupported conversion {from_unit}->{to_unit}; supported: {sorted(_UNITS)}")
        return f"{value * factor:.3f} {to_unit}"

    return mcp


if __name__ == "__main__":
    build_utils_server().run("stdio")
