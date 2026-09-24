"""LLM interface: har provider isi shape ko implement karta hai."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import LLMResponse, Message, ToolSpec


class LLM(ABC):
    provider: str = "base"
    model: str = ""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Messages bhejo, ek response lo (text ya tool calls)."""

    def complete(self, prompt: str, system: str | None = None, **kw) -> str:
        """Shortcut: ek prompt -> ek text answer. Simple chains ke liye."""
        msgs = ([Message.system(system)] if system else []) + [Message.user(prompt)]
        return self.chat(msgs, **kw).content or ""

    def __repr__(self) -> str:
        return f"<{self.provider}:{self.model}>"
