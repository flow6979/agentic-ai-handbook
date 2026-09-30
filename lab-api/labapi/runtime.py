"""Lab runtime: UI (agent-lab website) aur handbook projects ke beech ka pul.

Website ka Web Worker Pyodide mein yeh code chalata hai. Har request mein aata hai:
    {"lab": "react", "params": {...}, "llm": {"spec": "groq:llama-3.3-70b-versatile",
     "keys": {"groq": "gsk_..."}}, "offline": false, "lang": "hi"}

Lab chalte waqt `emit(event)` se har step turant UI ko jaata hai (live trace), aur end mein
ek result dict return hota hai. Keys sirf is request ki memory mein rehti hain.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agentkit import LLM, LLMResponse, NullTracer, get_embedder, get_llm

Emit = Callable[[dict[str, Any]], None]

# Handbook repo ka root (lab-api/labapi/runtime.py -> 2 level upar)
ROOT = Path(__file__).resolve().parents[2]


def use_project(rel_dir: str) -> Path:
    """Project folder ko sys.path mein daalo taaki uske modules import ho sakein.

    Har project ke module names repo mein unique hain (e.g. react_textloop.py), isliye
    kai projects ek saath path pe rahein to bhi clash nahi hota. `main.py` kabhi import mat karo.
    """
    p = ROOT / rel_dir
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    return p


@dataclass
class LabContext:
    params: dict[str, Any]
    llm_spec: str | None = None
    api_keys: dict[str, str] = field(default_factory=dict)
    embed_spec: str | None = None
    offline: bool = False
    lang: str = "hi"
    emit: Emit = lambda ev: None

    @classmethod
    def from_request(cls, req: dict[str, Any], emit: Emit) -> "LabContext":
        llm = req.get("llm") or {}
        return cls(
            params=req.get("params") or {},
            llm_spec=llm.get("spec"),
            api_keys=llm.get("keys") or {},
            embed_spec=llm.get("embed"),
            offline=bool(req.get("offline")),
            lang=req.get("lang", "hi"),
            emit=emit,
        )

    # --- helpers labs use -------------------------------------------------
    def llm(self, role: str | None = None, *, retries: int = 2) -> LLM:
        """Real LLM banao. `role` ke liye params mein `models.<role>` ho to woh spec use hota hai."""
        spec = (self.params.get("models") or {}).get(role) if role else None
        return MeteredLLM(get_llm(spec or self.llm_spec, retries=retries, api_keys=self.api_keys), self.emit, role)

    def embedder(self):
        spec = self.embed_spec or "local"
        real = get_embedder(spec, api_key=self._key_for(spec))
        return real if spec == "local" else _FallbackEmbedder(real, spec, self.emit)

    def _key_for(self, spec: str | None) -> str | None:
        if not spec or ":" not in spec:
            return None
        return self.api_keys.get(spec.split(":", 1)[0])

    def tracer(self, name: str) -> NullTracer:
        """agentkit Tracer jo har event ko UI tak bhejta hai (type = 'trace')."""
        return NullTracer(name=name, on_event=lambda ev: self.emit({"type": "trace", "agent": name, **ev}))

    def step(self, kind: str, text: str, **data: Any) -> None:
        """Lab-specific UI event, e.g. step('thought', '...') ya step('chunk', '...', score=0.8)."""
        self.emit({"type": "step", "kind": kind, "text": text, **data})


class _FallbackEmbedder:
    """Provider ka embedding model fail ho (e.g. model retire ho gaya, 404) to local hashing embedder.

    Beech mein switch karna mixed vectors bana deta, isliye pehli failure pe hi poora local pe jaate hain
    aur UI ko 'warning' event bhejte hain.
    """

    def __init__(self, real, spec: str, emit: Emit):
        self.real, self.spec, self.emit = real, spec, emit
        self.active = real
        self.dim = getattr(real, "dim", 0)

    def embed(self, texts):
        if self.active is self.real:
            try:
                return self.real.embed(texts)
            except Exception as e:  # noqa: BLE001 - kisi bhi provider error pe local
                from agentkit import get_embedder as _ge

                self.active = _ge("local")
                self.dim = self.active.dim
                self.emit({"type": "warning", "text": f"{self.spec} embeddings failed ({str(e)[:160]}); using the local embedder instead"})
        return self.active.embed(texts)

    def embed_one(self, text):
        return self.embed([text])[0]


class MeteredLLM(LLM):
    """LLM wrapper: har call ka latency + tokens UI ko bhejta hai, aur totals jodta hai."""

    def __init__(self, inner: LLM, emit: Emit, role: str | None = None):
        self.inner, self.emit, self.role = inner, emit, role
        self.provider, self.model = inner.provider, inner.model
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.ms = 0.0

    def chat(self, messages, tools=None, **kw) -> LLMResponse:
        t0 = time.perf_counter()
        resp = self.inner.chat(messages, tools, **kw)
        ms = (time.perf_counter() - t0) * 1000
        self.calls += 1
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        self.ms += ms
        self.emit({"type": "llm_call", "n": self.calls, "role": self.role, "model": resp.model or self.model,
                   "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
                   "ms": round(ms), "tool_calls": len(resp.tool_calls)})
        return resp

    def stats(self) -> dict[str, Any]:
        return {"llm_calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "ms": round(self.ms)}


def meter(llm: LLM, emit: Emit, role: str | None = None) -> MeteredLLM:
    """Offline ScriptedLLM ko bhi meter karo taaki UI mein same stats dikhein."""
    return llm if isinstance(llm, MeteredLLM) else MeteredLLM(llm, emit, role)
