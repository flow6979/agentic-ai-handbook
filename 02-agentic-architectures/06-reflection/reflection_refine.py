"""Reflection pattern 1: Generate -> Critique -> Revise (self-refine).

    draft = generate(task)
    loop:
        critique = critic(draft)      # structured: score, issues, approved
        if approved: stop
        draft = revise(draft, critique.issues)

Generator aur critic same LLM ho sakte hain (alag prompts/roles ke saath) ya alag models.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agentkit import LLM, NullTracer, Tracer, llm_json


class Critique(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall quality 1-10")
    issues: list[str] = Field(default_factory=list, description="Specific, actionable problems")
    approved: bool = Field(description="True only if the draft fully satisfies every requirement")


@dataclass
class RefineRound:
    draft: str
    critique: Critique


@dataclass
class RefineResult:
    final: str
    rounds: list[RefineRound] = field(default_factory=list)
    approved: bool = False


GEN_SYSTEM = "You are a skilled writer. Follow every requirement exactly. Output only the text."
CRITIC_SYSTEM = (
    "You are a strict reviewer. Check the draft against EVERY requirement in the task. "
    "List concrete, actionable issues (not vague praise). Approve only if nothing important is missing."
)


def self_refine(llm: LLM, task: str, *, max_rounds: int = 3, min_score: int = 9,
                critic_llm: LLM | None = None, tracer: Tracer | None = None) -> RefineResult:
    tracer = tracer or NullTracer(name="refine")
    critic_llm = critic_llm or llm
    draft = llm.complete(f"Task:\n{task}", system=GEN_SYSTEM)
    result = RefineResult(final=draft)

    for i in range(max_rounds):
        crit = llm_json(critic_llm, f"Task:\n{task}\n\nDraft:\n{draft}", Critique, system=CRITIC_SYSTEM)
        result.rounds.append(RefineRound(draft, crit))
        tracer.event("info", f"round {i + 1}: score={crit.score} approved={crit.approved} issues={crit.issues}")
        if crit.approved or crit.score >= min_score:
            result.final, result.approved = draft, True
            return result
        issues = "\n".join(f"- {x}" for x in crit.issues)
        draft = llm.complete(
            f"Task:\n{task}\n\nYour previous draft:\n{draft}\n\nReviewer issues:\n{issues}\n\n"
            "Rewrite the draft fixing every issue. Output only the new text.",
            system=GEN_SYSTEM,
        )
        tracer.event("llm", f"revised draft: {draft}")

    result.final = draft  # rounds khatam: last revision return karo (un-reviewed)
    return result
