"""A2A client (sync, httpx): card fetch, message/send, message/stream (SSE), tasks/get, tasks/cancel.

    c = A2AClient("http://127.0.0.1:9001")
    card = c.card                         # discovery
    task = c.send("convert 100 USD to INR")
    if task.status.state == "input-required":
        task = c.send("INR", task_id=task.id)
    for ev in c.stream("tips for Tokyo"):  # live events
        print(ev.kind)

Tests mein `http=TestClient(app)` pass karte hain (TestClient bhi httpx.Client hai) -> no network.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from typing import Any, Iterator

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))

from a2a_protocol import (TERMINAL, AgentCard, DataPart, Message, Task, TaskState, TextPart,  # noqa: E402
                          parse_event)

CARD_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")  # v0.3+ pehle, phir v0.2


class A2AError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"A2A error {code}: {message}")
        self.code, self.message, self.data = code, message, data


class A2AClient:
    def __init__(self, base_url: str, *, http: httpx.Client | None = None, token: str | None = None, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=timeout)
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._card: AgentCard | None = None
        self._ids = itertools.count(1)

    # ---------------------------------------------------------------- discovery
    @property
    def card(self) -> AgentCard:
        if self._card is None:
            last = None
            for path in CARD_PATHS:
                r = self.http.get(self.base_url + path, headers=self.headers)
                if r.status_code == 200:
                    self._card = AgentCard.model_validate(r.json())
                    break
                last = r
            else:
                raise A2AError(-1, f"no agent card at {self.base_url} (last status {last.status_code if last else '?'})")
        return self._card

    # ---------------------------------------------------------------- JSON-RPC
    def _body(self, method: str, params: dict) -> dict:
        return {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}

    def _rpc(self, method: str, params: dict) -> dict:
        r = self.http.post(self.card.url, json=self._body(method, params), headers=self.headers)
        if r.status_code == 401:
            raise A2AError(401, "unauthorized: this agent requires a bearer token (see card.securitySchemes)")
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            e = data["error"]
            raise A2AError(e["code"], e["message"], e.get("data"))
        return data["result"]

    @staticmethod
    def build_message(text: str | None = None, *, data: dict | None = None, task_id: str | None = None,
                      context_id: str | None = None) -> Message:
        parts: list = []
        if text:
            parts.append(TextPart(text=text))
        if data:
            parts.append(DataPart(data=data))
        return Message(role="user", parts=parts, task_id=task_id, context_id=context_id)

    def send(self, text: str | None = None, *, data: dict | None = None, task_id: str | None = None,
             context_id: str | None = None, blocking: bool = True, history_length: int | None = None) -> Task | Message:
        msg = self.build_message(text, data=data, task_id=task_id, context_id=context_id)
        config: dict[str, Any] = {"blocking": blocking}
        if history_length is not None:
            config["historyLength"] = history_length
        return parse_event(self._rpc("message/send", {"message": msg.wire(), "configuration": config}))

    def stream(self, text: str | None = None, *, data: dict | None = None, task_id: str | None = None,
               context_id: str | None = None) -> Iterator[Any]:
        if not self.card.capabilities.streaming:
            raise A2AError(-32004, f"{self.card.name} does not support streaming")
        msg = self.build_message(text, data=data, task_id=task_id, context_id=context_id)
        body = self._body("message/stream", {"message": msg.wire()})
        with self.http.stream("POST", self.card.url, json=body, headers=self.headers) as r:
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("text/event-stream"):  # error aaya, stream nahi
                data_ = json.loads(r.read())
                raise A2AError(data_["error"]["code"], data_["error"]["message"])
            for line in r.iter_lines():
                if line.startswith("data:"):
                    yield parse_event(json.loads(line[5:].strip())["result"])

    def get_task(self, task_id: str, history_length: int | None = None) -> Task:
        params: dict[str, Any] = {"id": task_id}
        if history_length is not None:
            params["historyLength"] = history_length
        return Task.model_validate(self._rpc("tasks/get", params))

    def cancel(self, task_id: str) -> Task:
        return Task.model_validate(self._rpc("tasks/cancel", {"id": task_id}))

    def wait(self, task_id: str, *, poll: float = 0.2, timeout: float = 120) -> Task:
        """Non-blocking send ke baad polling (push notifications ka simple alternative)."""
        deadline = time.time() + timeout
        while True:
            t = self.get_task(task_id)
            if t.status.state in TERMINAL or t.status.state == TaskState.input_required:
                return t
            if time.time() > deadline:
                raise TimeoutError(f"task {task_id} still {t.status.state.value}")
            time.sleep(poll)


def task_answer(task: Task) -> str:
    """Task se human-readable jawab: artifacts ka text, warna status message."""
    texts = [p.text for a in (task.artifacts or []) for p in a.parts if isinstance(p, TextPart)]
    if texts:
        return "\n".join(texts)
    return task.status.message.text() if task.status.message else ""


def task_data(task: Task) -> dict:
    out: dict = {}
    for a in task.artifacts or []:
        for p in a.parts:
            if isinstance(p, DataPart):
                out.update(p.data)
    return out
