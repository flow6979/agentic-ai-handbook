"""Async pub/sub event bus (asyncio) with retries, dead-letter queue, idempotency.

Pub/Sub mein publisher ko pata hi nahi hota ki kaun sun raha hai:
    publish("order.created", {...})   -> bus -> har matching subscriber ki queue

Har subscriber ki APNI queue + worker hoti hai (Kafka 'consumer group' jaisa), taaki ek slow
agent baaki ko block na kare.

Delivery guarantee: AT-LEAST-ONCE
    handler fail -> retry (max_attempts tak, backoff ke saath) -> phir bhi fail -> DEAD LETTER
    Isliye duplicate delivery possible hai -> consumers IDEMPOTENT hone chahiye
    (`idempotent()` wrapper: same idempotency_key dobara aaye to skip).

Real brokers mapping CONCEPTS.md mein hai (Redis Streams, Kafka, RabbitMQ, SQS).
"""
from __future__ import annotations

import asyncio
import fnmatch
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

Handler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    topic: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    idempotency_key: str = ""  # business key, e.g. "order-42:created"
    attempts: int = 0
    ts: float = field(default_factory=time.time)

    def __post_init__(self):
        self.idempotency_key = self.idempotency_key or self.id


@dataclass
class DeadLetter:
    subscriber: str
    event: Event
    error: str


@dataclass
class _Subscription:
    name: str
    pattern: str
    handler: Handler
    max_attempts: int
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


class EventBus:
    def __init__(self, backoff: float = 0.01):
        self._subs: list[_Subscription] = []
        self.backoff = backoff
        self.dead_letters: list[DeadLetter] = []
        self.log: list[tuple[str, str, str]] = []  # (event_id, subscriber, outcome)
        self.published: list[Event] = []
        self._started = False

    def subscribe(self, pattern: str, handler: Handler, *, name: str, max_attempts: int = 3) -> None:
        """pattern: exact 'order.created' ya wildcard 'order.*'"""
        sub = _Subscription(name, pattern, handler, max_attempts)
        self._subs.append(sub)
        if self._started:  # bus pehle se chal raha hai -> is subscriber ka worker abhi start karo
            sub.task = asyncio.create_task(self._worker(sub), name=f"sub:{name}")

    async def publish(self, topic: str, payload: dict[str, Any], *, idempotency_key: str = "") -> Event:
        ev = Event(topic, payload, idempotency_key=idempotency_key)
        self.published.append(ev)
        for s in self._subs:
            if fnmatch.fnmatch(topic, s.pattern):
                # Har subscriber ko apni copy (attempts alag count honge)
                await s.queue.put(Event(ev.topic, ev.payload, ev.id, ev.idempotency_key, 0, ev.ts))
        return ev

    async def _worker(self, s: _Subscription) -> None:
        while True:
            ev: Event = await s.queue.get()
            try:
                ev.attempts += 1
                await s.handler(ev)
                self.log.append((ev.id, s.name, "ok"))
            except Exception as e:
                if ev.attempts < s.max_attempts:
                    self.log.append((ev.id, s.name, f"retry {ev.attempts}: {e}"))
                    await asyncio.sleep(self.backoff * 2 ** (ev.attempts - 1))  # exponential backoff
                    await s.queue.put(ev)  # re-deliver (at-least-once)
                else:
                    self.log.append((ev.id, s.name, f"dead-letter: {e}"))
                    self.dead_letters.append(DeadLetter(s.name, ev, f"{type(e).__name__}: {e}"))
            finally:
                s.queue.task_done()

    async def start(self) -> None:
        self._started = True
        for s in self._subs:
            if s.task is None:
                s.task = asyncio.create_task(self._worker(s), name=f"sub:{s.name}")

    async def wait_idle(self) -> None:
        """Jab tak saari queues khaali na ho jayein (naye published events bhi) wait karo."""
        while any(not s.queue.empty() or s.queue._unfinished_tasks for s in self._subs):  # noqa: SLF001
            await asyncio.gather(*(s.queue.join() for s in self._subs))

    async def stop(self) -> None:
        self._started = False
        for s in self._subs:
            if s.task:
                s.task.cancel()
        await asyncio.gather(*(s.task for s in self._subs if s.task), return_exceptions=True)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()


def idempotent(handler: Handler, seen: set[str] | None = None) -> Handler:
    """Consumer-side dedupe: same idempotency_key dobara aaye to kuch mat karo.

    Production mein `seen` ek DB table / Redis SET hota hai (TTL ke saath), memory nahi.
    """
    seen = seen if seen is not None else set()

    async def wrapped(ev: Event) -> None:
        if ev.idempotency_key in seen:
            return
        await handler(ev)
        seen.add(ev.idempotency_key)  # SUCCESS ke baad hi mark karo, warna retry skip ho jayega

    wrapped.seen = seen  # type: ignore[attr-defined]
    return wrapped
