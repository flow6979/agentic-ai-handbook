"""@tool decorator: ek normal Python function ko LLM-callable tool banao.

LLM ko tool ke baare mein 3 cheezein chahiye: naam, description, aur arguments ka
JSON Schema. Hum yeh sab function ke signature + type hints + docstring se
automatically nikaal lete hain.

    @tool
    def get_weather(city: str, unit: Literal["c", "f"] = "c") -> str:
        '''Get current weather for a city.'''
        ...
"""
from __future__ import annotations

import inspect
import json
import types
import typing
from dataclasses import dataclass
from typing import Any, Callable, Literal, get_args, get_origin

from .llm.types import ToolSpec

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object"}


def _schema_for(tp: Any) -> dict[str, Any]:
    origin = get_origin(tp)
    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}
    if origin is Literal:
        return {"type": "string", "enum": list(get_args(tp))}
    if origin in (list, typing.List):
        (item,) = get_args(tp) or (str,)
        return {"type": "array", "items": _schema_for(item)}
    if origin in (dict, typing.Dict):
        return {"type": "object"}
    if origin in (typing.Union, types.UnionType):  # Optional[X] = Union[X, None]
        non_none = [a for a in get_args(tp) if a is not type(None)]
        return _schema_for(non_none[0])
    return {"type": "string"}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.parameters)

    def run(self, arguments: dict[str, Any]) -> str:
        """Tool chalao; result hamesha string (LLM text hi padhta hai)."""
        result = self.fn(**arguments)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)


def tool(fn: Callable | None = None, *, name: str | None = None, description: str | None = None):
    def wrap(f: Callable) -> Tool:
        hints = typing.get_type_hints(f)
        sig = inspect.signature(f)
        props, required = {}, []
        for pname, p in sig.parameters.items():
            props[pname] = _schema_for(hints.get(pname, str))
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        return Tool(
            name=name or f.__name__,
            description=description or inspect.getdoc(f) or f.__name__,
            parameters={"type": "object", "properties": props, "required": required},
            fn=f,
        )

    return wrap(fn) if fn else wrap
