"""Provider-neutral data types.

Har provider (OpenAI, Anthropic, Gemini, Groq, Ollama...) ka request/response format
alag hota hai. Hum apne agent code ko in neutral types pe likhte hain, aur har provider
adapter inhe apne format mein translate karta hai. Isse agent ko pata hi nahi chalta
ki peeche kaunsa LLM hai.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    """LLM ne bola: 'yeh tool, in arguments ke saath chalao'."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # sirf assistant messages mein
    tool_call_id: str | None = None  # sirf tool messages mein: kis call ka result hai
    name: str | None = None  # tool ka naam (tool messages ke liye)

    @staticmethod
    def system(text: str) -> "Message":
        return Message("system", text)

    @staticmethod
    def user(text: str) -> "Message":
        return Message("user", text)

    @staticmethod
    def assistant(text: str | None, tool_calls: list[ToolCall] | None = None) -> "Message":
        return Message("assistant", text, tool_calls=tool_calls)

    @staticmethod
    def tool(call: ToolCall, result: str) -> "Message":
        return Message("tool", result, tool_call_id=call.id, name=call.name)


@dataclass
class ToolSpec:
    """Tool ka description jo LLM ko bheja jata hai (name + JSON schema)."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    stop_reason: str = ""
    raw: Any = None  # provider ka original response, debugging ke liye

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMError(Exception):
    """Provider call fail hui. `retryable` batata hai ki dobara try karna chahiye ya nahi."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
