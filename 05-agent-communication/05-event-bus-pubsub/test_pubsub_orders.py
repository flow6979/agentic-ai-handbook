import asyncio

from agentkit import ScriptedLLM
from pubsub_bus import EventBus, idempotent
from pubsub_orders import SmsGateway, wire


def fake_llm():
    def fake(messages, tools):
        p = messages[-1].content or ""
        if "fraud risk" in p:
            return '{"risk": "high", "reason": "x"}' if "999999" in p else '{"risk": "low", "reason": "ok"}'
        return "sms text"

    return ScriptedLLM(fake)


def order(oid, amount=100, phone="9000000000"):
    return {"order_id": oid, "customer": "c", "phone": phone, "amount": amount}


async def run_pipeline(orders, gateway, duplicates=()):
    async with EventBus(backoff=0) as bus:
        agents = wire(bus, fake_llm(), gateway)
        for o in [*orders, *duplicates]:
            await bus.publish("order.created", o, idempotency_key=f"{o['order_id']}:created")
        await bus.wait_idle()
    return bus, agents


def test_fanout_routing_and_wildcard_analytics():
    gw = SmsGateway()
    bus, agents = asyncio.run(run_pipeline([order("O-1"), order("O-2", amount=999999)], gw))
    topics = [e.topic for e in bus.published]
    assert topics.count("order.approved") == 1 and topics.count("order.flagged") == 1
    assert len(gw.sent) == 2
    assert agents["analytics"].counts == {"order.created": 2, "order.approved": 1, "order.flagged": 1}


def test_duplicate_publish_is_processed_once():
    gw = SmsGateway()
    bus, agents = asyncio.run(run_pipeline([order("O-1")], gw, duplicates=[order("O-1")]))
    assert [e.topic for e in bus.published].count("order.created") == 2  # at-least-once: 2 deliveries
    assert [e.topic for e in bus.published].count("order.approved") == 1  # lekin fraud check ek hi baar
    assert len(gw.sent) == 1


def test_transient_failure_is_retried():
    gw = SmsGateway(fail_times=2)
    bus, _ = asyncio.run(run_pipeline([order("O-1")], gw))
    assert len(gw.sent) == 1 and bus.dead_letters == []
    assert [o for _, s, o in bus.log if s == "notify-approved"] == ["retry 1: gateway timeout", "retry 2: gateway timeout", "ok"]


def test_permanent_failure_goes_to_dead_letter_without_blocking_others():
    gw = SmsGateway()
    bus, _ = asyncio.run(run_pipeline([order("BAD", phone="000123"), order("O-2")], gw))
    assert len(bus.dead_letters) == 1
    dl = bus.dead_letters[0]
    assert dl.subscriber == "notify-approved" and dl.event.attempts == 3 and "invalid phone" in dl.error
    assert len(gw.sent) == 1  # O-2 ka SMS phir bhi gaya


def test_idempotent_marks_only_after_success():
    calls = []

    async def flaky(ev):
        calls.append(ev.id)
        if len(calls) == 1:
            raise RuntimeError("first fails")

    async def go():
        async with EventBus(backoff=0) as bus:
            h = idempotent(flaky)
            bus.subscribe("t", h, name="s")
            await bus.publish("t", {}, idempotency_key="k")
            await bus.wait_idle()
            return h

    h = asyncio.run(go())
    assert len(calls) == 2 and h.seen == {"k"}  # retry skip nahi hua
