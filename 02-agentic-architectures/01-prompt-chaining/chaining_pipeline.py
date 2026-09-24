"""Prompt chaining: ek bada kaam -> chhote sequential LLM steps, beech mein code 'gates'.

    topic -> [outline] -> GATE -> [draft per section] -> GATE -> [polish] -> blog post

Har step ka output agle step ka input hai. Gate = plain Python check jo galat output ko
aage badhne se rokta hai (fail -> retry us step ko feedback ke saath, ya pipeline rok do).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agentkit import LLM, ScriptedLLM, llm_json


class Outline(BaseModel):
    title: str
    sections: list[str] = Field(description="3 to 5 section headings, in reading order")


class GateError(Exception):
    """Gate fail hua: output quality bar pe nahi hai."""


@dataclass
class ChainResult:
    outline: Outline
    draft: str
    final: str
    log: list[str] = field(default_factory=list)  # har step ka short record (debugging/tracing)


# ---- Gates: pure code, no LLM -------------------------------------------------------------


def check_outline(o: Outline) -> None:
    if not 3 <= len(o.sections) <= 5:
        raise GateError(f"need 3-5 sections, got {len(o.sections)}")
    lowered = [s.strip().lower() for s in o.sections]
    if len(set(lowered)) != len(lowered):
        raise GateError("duplicate section headings")


def check_draft(draft: str, o: Outline, min_words: int = 40) -> None:
    missing = [s for s in o.sections if s.lower() not in draft.lower()]
    if missing:
        raise GateError(f"draft is missing sections: {missing}")
    if len(draft.split()) < min_words:
        raise GateError(f"draft too short ({len(draft.split())} words < {min_words})")


# ---- Steps: each one narrow LLM call -----------------------------------------------------


def step_outline(llm: LLM, topic: str, feedback: str = "") -> Outline:
    prompt = f"Create a blog post outline about: {topic}"
    if feedback:
        prompt += f"\nYour previous outline was rejected: {feedback}. Fix it."
    return llm_json(llm, prompt, Outline, system="You are a senior tech blog editor.")


def step_draft(llm: LLM, o: Outline, feedback: str = "") -> str:
    prompt = (
        f"Write a blog draft titled '{o.title}'. Use exactly these markdown '## ' headings in order:\n"
        + "\n".join(f"- {s}" for s in o.sections)
        + "\nKeep each section 2-4 sentences."
    )
    if feedback:
        prompt += f"\nPrevious draft was rejected: {feedback}. Fix it."
    return llm.complete(prompt, system="You are a clear, concise technical writer.")


def step_polish(llm: LLM, draft: str, tone: str) -> str:
    return llm.complete(
        f"Polish this draft for a {tone} tone. Keep all headings and facts; improve flow only.\n\n{draft}",
        system="You are a copy editor. Return only the polished post.",
    )


def run_step_with_gate(step, gate, max_attempts: int, log: list[str], label: str):
    """Step chalao, gate check karo; fail pe feedback ke saath retry. Yeh chaining ka core pattern hai."""
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        out = step(feedback)
        try:
            gate(out)
            log.append(f"{label}: ok (attempt {attempt})")
            return out
        except GateError as e:
            feedback = str(e)
            log.append(f"{label}: gate failed (attempt {attempt}): {e}")
    raise GateError(f"{label} failed after {max_attempts} attempts: {feedback}")


def write_blog(llm: LLM, topic: str, tone: str = "friendly", max_attempts: int = 2) -> ChainResult:
    log: list[str] = []
    outline = run_step_with_gate(lambda fb: step_outline(llm, topic, fb), check_outline, max_attempts, log, "outline")
    draft = run_step_with_gate(lambda fb: step_draft(llm, outline, fb), lambda d: check_draft(d, outline), max_attempts, log, "draft")
    final = step_polish(llm, draft, tone)
    log.append("polish: ok")
    return ChainResult(outline, draft, final, log)


# ---- Offline demo ------------------------------------------------------------------------

_DEMO_OUTLINE_BAD = {"title": "Python Async", "sections": ["Intro", "Basics", "intro"]}  # gate fail karega (duplicate)
_DEMO_OUTLINE = {"title": "Python Async for Beginners", "sections": ["Why async", "The event loop", "async and await", "When not to use it"]}
_DEMO_DRAFT = """## Why async
Network calls spend most time waiting. Async lets one thread do useful work while waiting.
## The event loop
The event loop is a scheduler. It runs a task until it awaits, then switches to another ready task.
## async and await
An async def function returns a coroutine. await pauses it until the awaited result is ready.
## When not to use it
CPU heavy work does not benefit. Use processes for that, and keep async for IO bound code."""


def offline_demo_llm() -> ScriptedLLM:
    return ScriptedLLM([
        json.dumps(_DEMO_OUTLINE_BAD),
        json.dumps(_DEMO_OUTLINE),
        _DEMO_DRAFT,
        _DEMO_DRAFT.replace("Network calls", "Most network calls").replace("CPU heavy", "CPU-heavy"),
    ])
