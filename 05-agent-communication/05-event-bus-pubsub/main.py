"""Order pipeline demo on an async event bus.

    python 05-agent-communication/05-event-bus-pubsub/main.py
    python 05-agent-communication/05-event-bus-pubsub/main.py --offline
"""
from __future__ import annotations

import argparse
import asyncio

from agentkit import ScriptedLLM, get_llm

from pubsub_bus import EventBus
from pubsub_orders import SmsGateway, wire

ORDERS = [
    {"order_id": "O-1", "customer": "Asha", "phone": "9876500001", "amount": 1200, "account_age_days": 400, "country": "IN", "card_country": "IN"},
    {"order_id": "O-2", "customer": "Rahul", "phone": "9876500002", "amount": 250000, "account_age_days": 1, "country": "IN", "card_country": "RU"},
    {"order_id": "O-3", "customer": "Test", "phone": "0000000000", "amount": 300, "account_age_days": 50, "country": "IN", "card_country": "IN"},
]


def offline_llm() -> ScriptedLLM:
    def fake(messages, tools):
        p = messages[-1].content or ""
        if "fraud risk" in p:
            high = "250000" in p
            return f'{{"risk": "{"high" if high else "low"}", "reason": "{"new account, huge amount, card country mismatch" if high else "normal pattern"}"}}'
        return "Hi! Your order update: " + ("confirmed" if "confirmed" in p else "on hold for review") + "."

    return ScriptedLLM(fake)


async def run(llm) -> None:
    gateway = SmsGateway(fail_times=1)  # pehla SMS transient fail hoga -> retry dikhega
    async with EventBus() as bus:
        agents = wire(bus, llm, gateway)
        for o in ORDERS:
            await bus.publish("order.created", o, idempotency_key=f"{o['order_id']}:created")
        # Producer retry simulate: O-1 dobara publish (network glitch ke baad)
        await bus.publish("order.created", ORDERS[0], idempotency_key="O-1:created")
        await bus.wait_idle()

    print("\n=== DELIVERY LOG (event, subscriber, outcome) ===")
    for row in bus.log:
        print(*row)
    print("\n=== SMS SENT ===")
    for phone, text in gateway.sent:
        print(phone, "->", text)
    print("\n=== ANALYTICS ===", dict(agents["analytics"].counts))
    print("\n=== DEAD LETTERS ===")
    for d in bus.dead_letters:
        print(d.subscriber, d.event.payload["order_id"], d.error, f"(attempts={d.event.attempts})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(offline_llm() if args.offline else get_llm()))


if __name__ == "__main__":
    main()
