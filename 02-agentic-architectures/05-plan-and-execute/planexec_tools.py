"""Trip-planning ke fake tools (deterministic data, taaki demo har baar same chale)."""
from __future__ import annotations

import ast
import operator

from agentkit import tool

WEATHER = {"goa": "sunny, 31C", "manali": "snow, -2C", "jaipur": "clear, 24C", "shimla": "cloudy, 8C"}
FLIGHTS = {
    ("delhi", "goa"): [{"airline": "IndiGo", "price_inr": 5400}, {"airline": "Air India", "price_inr": 6100}],
    ("delhi", "jaipur"): [{"airline": "IndiGo", "price_inr": 2900}],
}
HOTELS = {"goa": [{"name": "Beach Stay", "per_night_inr": 3500}], "jaipur": [{"name": "Pink Haveli", "per_night_inr": 2800}]}


@tool
def get_weather(city: str) -> str:
    """Current weather for an Indian city."""
    key = city.strip().lower()
    if key not in WEATHER:
        raise LookupError(f"weather service has no data for {city!r}")
    return WEATHER[key]


@tool
def search_flights(origin: str, destination: str) -> list:
    """Search flights between two cities. Returns a list of {airline, price_inr}."""
    key = (origin.strip().lower(), destination.strip().lower())
    if key not in FLIGHTS:
        raise LookupError(f"no flights from {origin} to {destination}")
    return FLIGHTS[key]


@tool
def search_hotels(city: str) -> list:
    """Search hotels in a city. Returns a list of {name, per_night_inr}."""
    return HOTELS.get(city.strip().lower(), [])


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _arith(node: ast.AST) -> float:
    """AST walk: sirf numbers aur + - * / allowed (LLM output ko kabhi eval() mat karo)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_arith(node.left), _arith(node.right))
    raise ValueError("only + - * / on numbers allowed")


@tool
def calculator(expression: str) -> str:
    """Add/multiply numbers, e.g. '5400 + 3*3500'. Supports + - * / and parentheses."""
    value = _arith(ast.parse(expression, mode="eval").body)
    return str(int(value) if float(value).is_integer() else round(value, 2))


TOOLS = [get_weather, search_flights, search_hotels, calculator]
