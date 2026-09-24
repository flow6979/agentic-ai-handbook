"""Offline 'fake brain': ScriptedLLM (function mode) jo real LLM jaisa behave karta hai.

Kaam: `--offline` demo, tests aur offline evals, bina API key / internet ke.
Yeh keyword rules pe chalta hai, intelligence nahi hai. Iska maqsad hai ki tum
POORA production pipeline (guards, tools, approval, memory, metrics) chalta hua dekh sako.
"""
from __future__ import annotations

import json
import re

from agentkit import LLMResponse, Message, ScriptedLLM, ToolSpec, call, tool_response

ORDER_RE = re.compile(r"\bORD-\d{4}\b", re.I)


def guess_intent(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(human|real person|manager|representative)\b", t):
        return "human_agent"
    if re.search(r"\b(refund|money back)\b", t) and ORDER_RE.search(text):
        return "refund"
    if re.search(r"\b(where|track|tracking|status|arrive|delivered)\b", t) and ORDER_RE.search(text):
        return "order_status"
    if re.search(r"\b(poem|joke|weather|code|python|capital of|song)\b", t):
        return "off_topic"
    if re.fullmatch(r"\s*(hi|hello|hey|thanks|thank you|bye)[!. ]*", t):
        return "greeting"
    return "faq"


def _compose(tool_name: str, content: str) -> str:
    if content.startswith("ERROR"):
        if "rejected" in content:
            return ("This refund needs a manual review, so I've escalated it to a human agent. "
                    "They will get back to you within 24 hours.")
        return "Sorry, something went wrong while checking that. Please try again in a moment."
    data = json.loads(content)
    if tool_name in ("track_shipment", "lookup_order"):
        if not data.get("found"):
            return "I couldn't find that order on your account. Please double-check the order ID."
        if tool_name == "lookup_order":
            o = data["order"]
            return f"Order {o['id']} ({o['item']}, ${o['amount']:.2f}) is currently {o['status']}."
        if data.get("carrier"):
            return (f"Your order {data['order_id']} is currently {data['status']} via {data['carrier']} "
                    f"(tracking {data['tracking_no']}). Latest update: {data['last_event']}. ETA: {data['eta']}.")
        return f"Your order {data['order_id']} is currently {data['status']} and hasn't shipped yet."
    if tool_name == "search_faq":
        results = data.get("results") or []
        return results[0]["answer"] if results else "I couldn't find an answer to that in our help center."
    if tool_name == "issue_refund":
        if data.get("ok"):
            return f"Done! I've issued a refund of ${data['amount']:.2f} for {data['order_id']}. {data['message']}"
        return f"I couldn't process that refund: {data['error']}"
    return content


def _brain(messages: list[Message], tools: list[ToolSpec] | None) -> str | LLMResponse:
    last = messages[-1]
    text = last.content or ""

    # 1) Structured-output calls (no tools): intent classifier / summarizer
    if not tools:
        if "Classify the customer's message" in text:
            msg = text.split("<<<", 1)[-1].split(">>>", 1)[0]
            return json.dumps({"intent": guess_intent(msg), "confidence": 0.9})
        if text.startswith("Summarize the conversation"):
            ids = sorted(set(ORDER_RE.findall(text)))
            return f"Customer discussed orders {', '.join(ids) or 'none'}; all questions were answered."
        return "OK"

    # 2) Agent loop: tool result aaya -> final answer
    if last.role == "tool":
        return _compose(last.name or "", text)

    # 3) Agent loop: naya user message -> kaunsa tool?
    m = ORDER_RE.search(text)
    oid = m.group(0).upper() if m else None
    intent = guess_intent(text)
    names = {t.name for t in tools}
    if intent == "greeting":
        return "Hi! How can I help you with your ShopKart orders today?"
    if intent == "refund":
        if "issue_refund" not in names:
            return "I can't issue refunds right now, but a human agent can help. Please reply 'human'."
        return tool_response(call("issue_refund", order_id=oid, reason=text[:120]))
    if intent == "order_status":
        return tool_response(call("track_shipment", order_id=oid))
    if oid:
        return tool_response(call("lookup_order", order_id=oid))
    return tool_response(call("search_faq", query=text))


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM(_brain, model="offline-fake")
