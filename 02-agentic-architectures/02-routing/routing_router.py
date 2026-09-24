"""Routing: input ko classify karo, phir sahi specialised handler ke paas bhejo.

Is file mein 3 router types + model routing:

  1. rule_route    -> keywords/regex. Free, instant, predictable. Lekin brittle.
  2. llm_route     -> LLM classifier (structured JSON: route + confidence + reason).
  3. hybrid_route  -> pehle rules (sasta), match nahi hua to LLM; low confidence -> human.
  4. pick_model    -> 'model routing': easy query sasta model, hard query strong model.

Router ke baad har route ka apna handler hai (alag system prompt, alag model tier).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from agentkit import LLM, ScriptedLLM, llm_json

RouteName = Literal["billing", "technical", "refund", "general"]


class RouteDecision(BaseModel):
    route: RouteName
    confidence: float = Field(ge=0, le=1)
    reason: str


# ---- 1) Rule-based router ------------------------------------------------------------------

RULES: list[tuple[RouteName, re.Pattern]] = [
    ("refund", re.compile(r"\b(refund|money back|return (my|the) order|chargeback)\b", re.I)),
    ("billing", re.compile(r"\b(invoice|billing|charged|payment|card|subscription|gst)\b", re.I)),
    ("technical", re.compile(r"\b(error|bug|crash|login|password|not working|500|timeout)\b", re.I)),
]


def rule_route(text: str) -> RouteDecision | None:
    """Pehla matching rule jeetega (order matter karta hai: refund > billing)."""
    for route, pattern in RULES:
        m = pattern.search(text)
        if m:
            return RouteDecision(route=route, confidence=1.0, reason=f"rule matched '{m.group(0)}'")
    return None


# ---- 2) LLM router ----------------------------------------------------------------------------

ROUTER_SYSTEM = """You are a support ticket router. Categories:
- billing: invoices, payments, charges, subscriptions
- technical: bugs, errors, login problems, app not working
- refund: customer wants money back or to return an order
- general: anything else (feedback, product questions, greetings)
Pick exactly one. Give honest confidence (0-1)."""


def llm_route(llm: LLM, text: str) -> RouteDecision:
    return llm_json(llm, f"Ticket:\n{text}", RouteDecision, system=ROUTER_SYSTEM)


# ---- 3) Hybrid router -------------------------------------------------------------------------


@dataclass
class Routed:
    decision: RouteDecision
    method: Literal["rule", "llm", "fallback"]
    needs_human: bool = False


def hybrid_route(llm: LLM, text: str, min_confidence: float = 0.6) -> Routed:
    d = rule_route(text)
    if d:
        return Routed(d, "rule")
    try:
        d = llm_route(llm, text)
    except ValueError:  # LLM valid JSON nahi de paya -> safe default
        return Routed(RouteDecision(route="general", confidence=0.0, reason="router failed"), "fallback", True)
    if d.confidence < min_confidence:
        return Routed(d, "llm", needs_human=True)
    return Routed(d, "llm")


# ---- 4) Model routing (cheap vs strong) -------------------------------------------------------


def complexity_score(text: str) -> int:
    """Simple heuristic. Production mein yeh ek chhota classifier ya LLM bhi ho sakta hai."""
    score = 0
    score += len(text.split()) > 60
    score += len(re.findall(r"\?", text)) > 1
    score += bool(re.search(r"\b(why|compare|explain|debug|architecture|trade-?off)\b", text, re.I))
    score += bool(re.search(r"```|Traceback|Exception", text))
    return score


def pick_model(text: str, cheap: LLM, strong: LLM, threshold: int = 2) -> LLM:
    return strong if complexity_score(text) >= threshold else cheap


# ---- Handlers: har route ka specialised prompt ------------------------------------------------

HANDLER_PROMPTS: dict[str, str] = {
    "billing": "You are a billing specialist. Be precise about amounts and dates. Never promise refunds.",
    "technical": "You are a tier-2 support engineer. Ask for error messages, give numbered troubleshooting steps.",
    "refund": "You handle refunds. Explain the 7-day refund policy and ask for the order id if missing.",
    "general": "You are a friendly support agent. Keep it short.",
}


@dataclass
class TicketReply:
    route: str
    method: str
    model: str
    reply: str
    needs_human: bool


def handle_ticket(text: str, router_llm: LLM, cheap: LLM, strong: LLM) -> TicketReply:
    routed = hybrid_route(router_llm, text)
    if routed.needs_human:
        return TicketReply(routed.decision.route, routed.method, "-", "Escalated to a human agent.", True)
    model = pick_model(text, cheap, strong)
    reply = model.complete(text, system=HANDLER_PROMPTS[routed.decision.route])
    return TicketReply(routed.decision.route, routed.method, repr(model), reply, False)


# ---- Offline demo -----------------------------------------------------------------------------


def offline_router_llm() -> ScriptedLLM:
    def fake(messages, tools):
        t = messages[-1].content.lower()
        if "dark mode" in t:
            return json.dumps({"route": "general", "confidence": 0.9, "reason": "feature request"})
        if "weird" in t:
            return json.dumps({"route": "technical", "confidence": 0.4, "reason": "unclear"})
        return json.dumps({"route": "general", "confidence": 0.7, "reason": "default"})

    return ScriptedLLM(fake, model="router")


def offline_handler_llm(name: str) -> ScriptedLLM:
    return ScriptedLLM(lambda m, t: f"[{name}] reply using prompt: {m[0].content[:40]}...", model=name)
