"""Ping lab: 'Test connection' button. Chhota prompt bhejo, 'pong' ka intezaar karo."""
from __future__ import annotations

from agentkit import Message, ScriptedLLM

from .registry import Lab
from .runtime import LabContext, meter


def run(ctx: LabContext) -> dict:
    llm = meter(ScriptedLLM(["pong"], model="scripted"), ctx.emit) if ctx.offline else ctx.llm(retries=0)
    resp = llm.chat([Message.user("Reply with exactly one word: pong")], max_tokens=5)
    text = (resp.content or "").strip()
    return {"reply": text, "ok": "pong" in text.lower(), "provider": llm.provider, "model": resp.model or llm.model,
            **llm.stats()}


LAB = Lab(id="ping", project="common", run=run)
