"""Role design basics: ek 'role' kya hota hai, aur usse system prompt kaise banta hai.

Role = persona + goal + backstory + tools + allowed actions + output contract.
Yahan ek chhota 2-role system hai: Writer draft likhta hai, Editor review karta hai.
Editor structured verdict (JSON) deta hai, taaki code decide kar sake: approve ya revise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from agentkit import LLM, Agent, ScriptedLLM, Tool, Tracer, get_llm, llm_json


# --------------------------------------------------------------------------- roles
@dataclass
class Role:
    name: str  # "Writer" -- chhota, unique naam (routing/logging mein use hota hai)
    persona: str  # kaun hai: "a senior tech blogger"
    goal: str  # kya achieve karna hai (measurable ho to best)
    backstory: str = ""  # context jo tone/judgement shape karta hai
    tools: list[Tool] = field(default_factory=list)  # sirf wahi tools jo is role ko chahiye
    allowed_actions: list[str] = field(default_factory=list)  # kya kar sakta hai
    forbidden_actions: list[str] = field(default_factory=list)  # kya NAHI karna (role drift rokne ke liye)
    output_contract: str = "Plain text."  # output ka exact format

    def system_prompt(self) -> str:
        """Role -> system prompt. Har role ke liye same template = consistent behaviour."""
        lines = [
            f"ROLE: {self.name}",
            f"You are {self.persona}.",
            f"GOAL: {self.goal}",
        ]
        if self.backstory:
            lines.append(f"BACKSTORY: {self.backstory}")
        if self.allowed_actions:
            lines.append("YOU MAY: " + "; ".join(self.allowed_actions))
        if self.forbidden_actions:
            lines.append("YOU MUST NOT: " + "; ".join(self.forbidden_actions))
        if self.tools:
            lines.append("TOOLS: " + ", ".join(t.name for t in self.tools))
        lines.append(f"OUTPUT FORMAT: {self.output_contract}")
        lines.append("Stay strictly in your role. If a request is outside your role, say so briefly.")
        return "\n".join(lines)


def llm_for(role: str) -> LLM:
    """Per-role model: LLM_MODEL_WRITER=... set hai to woh, warna LLM_MODEL.

    Multi-LLM team: sasta fast model writer ke liye, strong model editor ke liye, etc.
    """
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


WRITER = Role(
    name="Writer",
    persona="a clear, friendly technical writer",
    goal="Write a short (under 120 words) explainer on the given topic for beginners",
    backstory="You have written docs for developer tools for 10 years and hate jargon.",
    allowed_actions=["draft text", "revise text based on editor feedback"],
    forbidden_actions=["approve your own work", "invent statistics"],
    output_contract="Only the article text. No preamble.",
)

EDITOR = Role(
    name="Editor",
    persona="a strict but fair copy editor",
    goal="Decide if the draft is accurate, clear and under 120 words; give actionable feedback",
    allowed_actions=["review", "approve", "request changes"],
    forbidden_actions=["rewrite the whole article yourself"],
    output_contract='JSON: {"approved": bool, "feedback": "one or two concrete fixes, empty if approved"}',
)


class EditorVerdict(BaseModel):
    approved: bool
    feedback: str = ""


# --------------------------------------------------------------------------- 2-role flow
@dataclass
class DraftResult:
    final_text: str
    rounds: int
    history: list[tuple[str, str]]  # (role, output) -- audit trail


def write_with_editor(
    topic: str,
    llm_factory: Callable[[str], LLM] = llm_for,
    max_revisions: int = 2,
    tracer: Tracer | None = None,
) -> DraftResult:
    writer_llm, editor_llm = llm_factory("writer"), llm_factory("editor")
    writer = Agent(writer_llm, WRITER.tools, WRITER.system_prompt(), name="writer", tracer=tracer or Tracer(name="writer"))
    history: list[tuple[str, str]] = []

    draft = writer.run(f"Topic: {topic}").output
    history.append(("Writer", draft))
    for round_no in range(1, max_revisions + 2):
        verdict = llm_json(editor_llm, f"Topic: {topic}\n\nDRAFT:\n{draft}", EditorVerdict, system=EDITOR.system_prompt())
        history.append(("Editor", verdict.model_dump_json()))
        if verdict.approved or round_no > max_revisions:  # termination: approve ya revision budget khatam
            return DraftResult(draft, round_no, history)
        # Writer ko sirf feedback + purana draft do (poori history nahi) -> context chhota, focused
        draft = writer.run(f"Topic: {topic}\n\nYour previous draft:\n{draft}\n\nEditor feedback: {verdict.feedback}\nRevise.").output
        history.append(("Writer", draft))
    return DraftResult(draft, max_revisions + 1, history)


# --------------------------------------------------------------------------- offline fake
def offline_llm() -> ScriptedLLM:
    """Bina API key ke chalne wala fake: system prompt ka ROLE dekh ke jawab deta hai."""
    state = {"editor_calls": 0}

    def respond(messages, tools):
        system = messages[0].content if messages and messages[0].role == "system" else ""
        if "ROLE: Editor" in system:
            state["editor_calls"] += 1
            if state["editor_calls"] == 1:
                return '{"approved": false, "feedback": "Add one concrete everyday example."}'
            return '{"approved": true, "feedback": ""}'
        last = messages[-1].content or ""
        if "Editor feedback" in last:
            return "An API is a menu for software: like ordering from a restaurant menu, your app asks for a dish and the kitchen (server) sends it back."
        return "An API lets one program ask another program for data or actions using agreed rules."

    return ScriptedLLM(respond)


# Anti-pattern examples (CONCEPTS.md mein explain kiye hain)
BAD_ROLE = Role(name="Helper", persona="a helpful AI", goal="help with everything")  # vague = role drift
