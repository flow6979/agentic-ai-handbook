"""Observability: request ids, structured JSON logs, token + cost accounting.

Har request ka ek request_id: logs, traces, API response sab mein same id. Customer
complain kare to us id se poori kahani (kaunse tools, kitne tokens, kya error) mil jaaye.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid

from agentkit import LLM, LLMResponse, Usage

# USD per 1M tokens (input, output). APPROXIMATE, sirf demo ke liye: provider ka pricing page se update karo.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-haiku": (1.00, 5.00),
    "claude-sonnet": (3.00, 15.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "llama-3.3-70b": (0.59, 0.79),
}


def estimate_cost(model: str, usage: Usage) -> float | None:
    """Model naam ke substring se price dhoondo. None = pata nahi (local models free hain)."""
    m = model.lower()
    for key in sorted(PRICES_PER_MTOK, key=len, reverse=True):  # longest match pehle: gpt-4o-mini before gpt-4o
        if key in m:
            pin, pout = PRICES_PER_MTOK[key]
            return round((usage.input_tokens * pin + usage.output_tokens * pout) / 1_000_000, 6)
    return None


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]


class MeteredLLM(LLM):
    """Wrapper jo ek request ke saare LLM calls (intent + agent + summary) ka usage jodta hai."""

    def __init__(self, inner: LLM):
        self.inner = inner
        self.provider, self.model = inner.provider, inner.model
        self.usage = Usage()
        self.calls = 0
        self.last_model = inner.model

    def chat(self, messages, tools=None, **kw) -> LLMResponse:
        r = self.inner.chat(messages, tools, **kw)
        self.usage = self.usage + r.usage
        self.calls += 1
        self.last_model = r.model or self.last_model
        return r


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        data.update(getattr(record, "fields", {}))
        return json.dumps(data, default=str)


def get_logger() -> logging.Logger:
    log = logging.getLogger("supportdesk")
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def log_event(log: logging.Logger, msg: str, **fields) -> None:
    log.info(msg, extra={"fields": fields})
