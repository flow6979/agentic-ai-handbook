"""Memory extraction: conversation se durable facts nikaalna (llm_json se structured output).

Har message save karna = kachra. Hum LLM se poochte hain: "is baatcheet mein user ke baare mein
kaunsi baatein future mein kaam aayengi?" Sirf wahi save hoti hain.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentkit import LLM, Message, llm_json


class Fact(BaseModel):
    text: str = Field(description="Short third-person statement, e.g. 'User is vegetarian'")
    category: Literal["preference", "personal", "work", "other"] = "other"


class Facts(BaseModel):
    facts: list[Fact] = Field(default_factory=list)


EXTRACT_SYSTEM = (
    "You extract long-term memories about the USER from a conversation. Keep only stable, useful facts "
    "(preferences, personal details they shared, work context, goals). Skip small talk, one-off requests "
    "and anything about the assistant. Return an empty list if there is nothing worth remembering."
)


def extract_facts(llm: LLM, transcript: list[Message]) -> list[Fact]:
    convo = "\n".join(f"{m.role}: {m.content}" for m in transcript if m.role in ("user", "assistant") and m.content)
    if not convo:
        return []
    return llm_json(llm, f"Conversation:\n{convo}", Facts, system=EXTRACT_SYSTEM).facts
