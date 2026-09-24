"""Intent classification with structured output (llm_json + Pydantic).

Code is output ko consume karta hai (routing ke liye), isliye free text nahi, validated JSON.
Sasta pre-step: off-topic / 'human chahiye' wale messages pe poora agent loop chalane ki
zaroorat hi nahi (cost + latency bachta hai).
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from agentkit import LLM, LLMError, llm_json

log = logging.getLogger("supportdesk.intent")

IntentName = Literal["order_status", "refund", "faq", "human_agent", "off_topic", "greeting"]


class Intent(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0, le=1)


PROMPT = """Classify the customer's message for an online store support desk.
Intents:
- order_status: where is my order, tracking, delivery status
- refund: wants money back / return an item
- faq: general store policy questions (returns, shipping times, payments, cancellation)
- human_agent: explicitly asks for a human / manager / real person
- off_topic: unrelated to the store (poems, coding, weather, trivia)
- greeting: hi / thanks / bye with no request
Message: <<<{text}>>>"""


def classify(llm: LLM, text: str) -> Intent:
    try:
        return llm_json(llm, PROMPT.format(text=text), Intent, retries=1)
    except ValueError as e:
        # Classifier fail = full agent ko handle karne do (safe default), request fail mat karo
        log.warning("intent classification failed, defaulting to faq: %s", e)
        return Intent(intent="faq", confidence=0.0)
    # LLMError (provider down) upar jaane do: service graceful degradation karega


__all__ = ["Intent", "classify", "LLMError"]
