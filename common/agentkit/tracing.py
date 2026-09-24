"""Tracer: agent ne har step pe kya socha, kya tool chalaya, kitne tokens lage.

Observability ke bina production agent 'black box' hai. Har event ko print bhi karte hain
(dev ke liye) aur optionally JSONL file mein likhte hain (baad mein analyse / eval ke liye).
LangSmith, Langfuse, Arize jaise tools yahi kaam bade scale pe karte hain.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

COLORS = {"llm": "\033[36m", "tool": "\033[33m", "result": "\033[32m", "error": "\033[31m", "info": "\033[35m"}
RESET = "\033[0m"


class Tracer:
    def __init__(self, verbose: bool | None = None, jsonl_path: str | None = None, name: str = "agent"):
        self.verbose = verbose if verbose is not None else os.getenv("AGENT_VERBOSE", "1") != "0"
        self.jsonl_path = jsonl_path or os.getenv("AGENT_TRACE_FILE")
        self.name = name
        self.events: list[dict[str, Any]] = []

    def event(self, kind: str, message: str, **data: Any) -> None:
        ev = {"ts": time.time(), "agent": self.name, "kind": kind, "message": message, **data}
        self.events.append(ev)
        if self.verbose:
            color = COLORS.get(kind, "")
            short = message if len(message) < 400 else message[:400] + "..."
            print(f"{color}[{self.name}:{kind}]{RESET} {short}", file=sys.stderr)
        if self.jsonl_path:
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(ev, default=str) + "\n")


class NullTracer(Tracer):
    def __init__(self, name: str = "agent"):
        super().__init__(verbose=False, jsonl_path=None, name=name)

    def event(self, kind: str, message: str, **data: Any) -> None:
        self.events.append({"kind": kind, "message": message, **data})
