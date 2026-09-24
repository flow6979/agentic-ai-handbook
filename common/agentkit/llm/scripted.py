"""ScriptedLLM: tests aur offline demos ke liye 'fake' LLM.

Production mein bhi agents ko test karne ka yahi tareeka hai: LLM ko mock karo taaki
test deterministic ho, free ho, aur internet ke bina chale. Hum sirf apna code
(loop, tools, parsing, routing) test karte hain, LLM ki intelligence nahi.

Do modes:
1. List of responses: har `chat()` call pe agla response.
2. Function: `fn(messages, tools) -> LLMResponse | str`, jisse smart fake bana sakte ho.
"""
from __future__ import annotations

import itertools
from typing import Callable, Union

from .base import LLM
from .types import LLMResponse, Message, ToolCall, ToolSpec, Usage

Scripted = Union[str, LLMResponse]
_ids = itertools.count(1)


def call(name: str, **arguments) -> ToolCall:
    """Test mein tool call banane ka shortcut: call('add', a=2, b=3)."""
    return ToolCall(id=f"call_{next(_ids)}", name=name, arguments=arguments)


def tool_response(*calls: ToolCall, text: str | None = None) -> LLMResponse:
    return LLMResponse(content=text, tool_calls=list(calls))


class ScriptedLLM(LLM):
    provider = "scripted"

    def __init__(
        self,
        script: list[Scripted] | Callable[[list[Message], list[ToolSpec] | None], Scripted],
        model: str = "fake",
    ):
        self.model = model
        self._script = script
        self._i = 0
        self.calls: list[list[Message]] = []  # har call pe kya bheja gaya, asserts ke liye

    def chat(self, messages, tools=None, *, temperature=0.0, max_tokens=1024, json_mode=False) -> LLMResponse:
        self.calls.append(list(messages))
        if callable(self._script):
            out = self._script(messages, tools)
        else:
            if self._i >= len(self._script):
                raise AssertionError(f"ScriptedLLM ran out of responses after {self._i} calls")
            out = self._script[self._i]
            self._i += 1
        if isinstance(out, str):
            out = LLMResponse(content=out)
        out.usage = out.usage if out.usage.input_tokens else Usage(sum(len(m.content or "") for m in messages) // 4, len(out.content or "") // 4)
        out.model = self.model
        return out
