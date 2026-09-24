"""Order pipeline: teen agents jo sirf events ke through baat karte hain.

    order.created ──► FraudCheckAgent (LLM) ──► order.approved | order.flagged
                                                     │
                     NotificationAgent (LLM) ◄───────┤   (SMS gateway flaky -> retry / DLQ)
                     AnalyticsAgent (no LLM) ◄── order.*  (sab kuch count karta hai)
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from agentkit import LLM, llm_json

from pubsub_bus import Event, EventBus, idempotent


class RiskVerdict(BaseModel):
    risk: Literal["low", "high"]
    reason: str


class FraudCheckAgent:
    def __init__(self, llm: LLM, bus: EventBus):
        self.llm, self.bus = llm, bus

    async def on_order_created(self, ev: Event) -> None:
        o = ev.payload
        # LLM call blocking hai -> thread mein chalao taaki event loop free rahe
        verdict = await asyncio.to_thread(
            llm_json, self.llm,
            f"Assess fraud risk for this order: {o}. New accounts with very large amounts or mismatched "
            f"country are high risk.", RiskVerdict, system="You are a fraud analyst.",
        )
        topic = "order.approved" if verdict.risk == "low" else "order.flagged"
        await self.bus.publish(topic, {**o, "reason": verdict.reason}, idempotency_key=f"{o['order_id']}:{topic}")


class SmsGateway:
    """Fake SMS provider. `fail_times` baar fail hota hai (transient), '000' numbers hamesha fail."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> None:
        if phone.startswith("000"):
            raise ValueError(f"invalid phone {phone}")
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("gateway timeout")
        self.sent.append((phone, text))


class NotificationAgent:
    def __init__(self, llm: LLM, gateway: SmsGateway):
        self.llm, self.gateway = llm, gateway

    async def on_decision(self, ev: Event) -> None:
        o = ev.payload
        status = "confirmed" if ev.topic == "order.approved" else "on hold for review"
        text = await asyncio.to_thread(
            self.llm.complete,
            f"Write a one-line SMS to {o['customer']} saying order {o['order_id']} is {status}.",
            system="You write short, polite SMS messages.",
        )
        await self.gateway.send(o["phone"], text.strip())


class AnalyticsAgent:
    def __init__(self):
        self.counts: Counter[str] = Counter()

    async def on_any(self, ev: Event) -> None:
        self.counts[ev.topic] += 1


def wire(bus: EventBus, llm: LLM, gateway: SmsGateway) -> dict:
    fraud, notify, analytics = FraudCheckAgent(llm, bus), NotificationAgent(llm, gateway), AnalyticsAgent()
    # idempotent(): producer ne same order do baar bheja to bhi fraud check/SMS ek hi baar
    bus.subscribe("order.created", idempotent(fraud.on_order_created), name="fraud")
    notify_handler = idempotent(notify.on_decision)
    bus.subscribe("order.approved", notify_handler, name="notify-approved", max_attempts=3)
    bus.subscribe("order.flagged", notify_handler, name="notify-flagged", max_attempts=3)
    bus.subscribe("order.*", idempotent(analytics.on_any), name="analytics")
    return {"fraud": fraud, "notify": notify, "analytics": analytics}
