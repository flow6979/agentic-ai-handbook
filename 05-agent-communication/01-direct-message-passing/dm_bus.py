"""Direct message passing: agents ek dusre ko typed 'envelopes' bhejte hain.

Envelope = chitthi ka lifafa. Andar payload (asli data), bahar address + metadata:
    sender, recipient, type (request/response/event), correlation_id, id, ts

Do communication styles:
    request()  -> synchronous: bhejo aur jawab ka wait karo (function call jaisa)
    send()     -> fire-and-forget: inbox mein daalo, jawab ki umeed nahi (event/notification)

MessageBus sirf "post office" hai: address dekh ke sahi agent tak pahunchata hai aur
har message ka log rakhta hai (debugging / tracing ke liye).
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

MsgType = Literal["request", "response", "event", "error"]


@dataclass
class Envelope:
    sender: str
    recipient: str
    type: MsgType
    payload: dict[str, Any]
    correlation_id: str | None = None  # response kis request ka hai
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    ts: float = field(default_factory=time.time)

    def reply(self, payload: dict[str, Any], type: MsgType = "response") -> "Envelope":
        """Response banao: sender/recipient ulte, correlation_id = original request ka id."""
        return Envelope(self.recipient, self.sender, type, payload, correlation_id=self.id)


class BusAgent:
    """Har agent ka base: ek naam, bus ka reference, aur handle()."""

    def __init__(self, name: str):
        self.name = name
        self.bus: MessageBus | None = None

    def handle(self, msg: Envelope) -> Envelope | None:  # pragma: no cover - override
        raise NotImplementedError

    # Agent khud bhi dusre agents ko call kar sakta hai (agent -> agent)
    def ask(self, recipient: str, payload: dict[str, Any]) -> Envelope:
        assert self.bus, f"{self.name} is not registered on a bus"
        return self.bus.request(Envelope(self.name, recipient, "request", payload))

    def tell(self, recipient: str, payload: dict[str, Any]) -> None:
        assert self.bus, f"{self.name} is not registered on a bus"
        self.bus.send(Envelope(self.name, recipient, "event", payload))


class MessageBus:
    def __init__(self, max_depth: int = 5):
        self.agents: dict[str, BusAgent] = {}
        self.log: list[Envelope] = []  # har message yahan record hota hai
        self._inbox: deque[Envelope] = deque()  # fire-and-forget queue
        self._depth = 0
        self.max_depth = max_depth  # A->B->A->B... infinite ping-pong se bachao

    def register(self, agent: BusAgent) -> None:
        agent.bus = self
        self.agents[agent.name] = agent

    def _deliver(self, msg: Envelope) -> Envelope | None:
        agent = self.agents.get(msg.recipient)
        if agent is None:
            return msg.reply({"error": f"no agent named {msg.recipient!r}"}, type="error")
        try:
            return agent.handle(msg)
        except Exception as e:  # agent crash hua -> error envelope, bus crash nahi
            return msg.reply({"error": f"{type(e).__name__}: {e}"}, type="error")

    def request(self, msg: Envelope) -> Envelope:
        """Synchronous request/response. Caller jawab aane tak ruka rehta hai."""
        if self._depth >= self.max_depth:
            return msg.reply({"error": "max call depth exceeded"}, type="error")
        self.log.append(msg)
        self._depth += 1
        try:
            resp = self._deliver(msg) or msg.reply({"error": "agent returned no response"}, type="error")
        finally:
            self._depth -= 1
        self.log.append(resp)
        return resp

    def send(self, msg: Envelope) -> None:
        """Fire-and-forget: sirf queue mein daalo. Delivery baad mein drain() pe hogi."""
        self.log.append(msg)
        self._inbox.append(msg)

    def drain(self) -> int:
        """Queue ke saare pending messages deliver karo. Kitne deliver hue, return."""
        n = 0
        while self._inbox:
            msg = self._inbox.popleft()
            self._deliver(msg)  # response ignore: fire-and-forget
            n += 1
        return n

    def conversation(self, correlation_id: str) -> list[Envelope]:
        """Ek request aur uska response dhoondo (tracing)."""
        return [m for m in self.log if m.id == correlation_id or m.correlation_id == correlation_id]
