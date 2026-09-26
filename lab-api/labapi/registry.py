"""Lab registry: `labapi/*_lab.py` files khud register ho jaati hain.

Har lab module ek `LAB = Lab(...)` define karta hai. Naya lab jodna = ek nayi file,
kisi shared list ko edit nahi karna padta.

`run(request, emit)` hamesha ek dict lautaata hai, kabhi exception nahi:
    {"ok": True, "result": {...}}
    {"ok": False, "error": {"kind": "auth|rate_limit|not_found|network|bad_request|internal",
                            "status": 401, "message": "..."}}
UI isi `kind` se sahi error screen (SetupErrors) dikhata hai.
"""
from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from agentkit import LLMError

from .runtime import Emit, LabContext


@dataclass
class Lab:
    id: str
    project: str  # handbook folder, e.g. "02-agentic-architectures/04-react"
    run: Callable[[LabContext], dict[str, Any]]
    live: bool = True  # False = sirf recorded replay (e.g. MCP/A2A servers browser mein nahi chal sakte)
    defaults: dict[str, Any] = field(default_factory=dict)


_LABS: dict[str, Lab] = {}


def _discover() -> None:
    if _LABS:
        return
    import labapi

    for mod in pkgutil.iter_modules(labapi.__path__):
        if mod.name.endswith("_lab"):
            m = importlib.import_module(f"labapi.{mod.name}")
            lab = getattr(m, "LAB", None)
            if isinstance(lab, Lab):
                _LABS[lab.id] = lab


def labs() -> dict[str, Lab]:
    _discover()
    return dict(_LABS)


def catalog() -> list[dict[str, Any]]:
    return [{"id": l.id, "project": l.project, "live": l.live, "defaults": l.defaults} for l in labs().values()]


def classify_error(e: BaseException) -> dict[str, Any]:
    if isinstance(e, LLMError):
        s = e.status
        kind = ("auth" if s in (401, 403) else "rate_limit" if s == 429 else "not_found" if s == 404
                else "bad_request" if s and 400 <= s < 500 else "network" if s is None else "server")
        return {"kind": kind, "status": s, "message": str(e)[:500]}
    if isinstance(e, ValueError) and "needs" in str(e) and "_API_KEY" in str(e):
        return {"kind": "auth", "status": None, "message": str(e)}
    return {"kind": "internal", "status": None, "message": f"{type(e).__name__}: {e}"[:500],
            "trace": traceback.format_exc()[-1500:]}


def run(request: dict[str, Any], emit: Emit) -> dict[str, Any]:
    lab_id = request.get("lab")
    lab = labs().get(lab_id)
    if lab is None:
        return {"ok": False, "error": {"kind": "bad_request", "status": None, "message": f"unknown lab {lab_id!r}"}}
    ctx = LabContext.from_request(request, emit)
    ctx.params = {**lab.defaults, **ctx.params}
    try:
        return {"ok": True, "result": lab.run(ctx)}
    except Exception as e:  # UI ko hamesha structured error chahiye
        err = classify_error(e)
        emit({"type": "error", **err})
        return {"ok": False, "error": err}
