"""Supervisor team (LangGraph-supervisor style, from scratch).

                 +-------------+
        +------->| SUPERVISOR  |-------- FINISH --> final answer
        |        +------+------+
        |   route (JSON)|  {"next": "researcher", "instruction": "..."}
        |      +--------+--------+
        |      v        v        v
        | researcher  writer   critic      <- workers (apne tools, apna prompt)
        |      |        |        |
        +------+--------+--------+  output shared 'board' pe jata hai

Termination guards:
  1. supervisor 'FINISH' bole
  2. max_rounds khatam
  3. same worker lagatar N baar (ping-pong / stuck loop) -> force finish
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Literal

from pydantic import BaseModel

from agentkit import LLM, Agent, ScriptedLLM, Tracer, call, get_llm, llm_json, tool, tool_response

WORKERS = ("researcher", "writer", "critic")


def llm_for(role: str) -> LLM:
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


# --------------------------------------------------------------------------- researcher's tool
KNOWLEDGE = {
    "solar": "Solar panels convert sunlight to electricity. Home systems typically pay back in 6-10 years. "
             "Output drops on cloudy days; batteries store surplus.",
    "wind": "Small wind turbines need average wind speeds above ~4 m/s to be worth it; noisy near homes.",
    "heat pump": "Heat pumps move heat instead of burning fuel; 3-4x more efficient than electric heaters.",
}


@tool
def search_notes(query: str) -> str:
    """Search the team's research notes for a topic keyword."""
    hits = [f"[{k}] {v}" for k, v in KNOWLEDGE.items() if k in query.lower() or query.lower() in k]
    return "\n".join(hits) or "No notes found. Try a simpler keyword like 'solar'."


# --------------------------------------------------------------------------- roles
PROMPTS = {
    "supervisor": (
        "ROLE: Supervisor\nYou manage a team: researcher (finds facts with a search tool), writer (writes the answer), "
        "critic (reviews the draft). Look at the work so far and pick who acts next, with a precise instruction. "
        "Typical order: research -> write -> critique -> (rewrite if critic found issues) -> FINISH. "
        "Pick FINISH only when the critic approved a draft."
    ),
    "researcher": "ROLE: Researcher\nFind facts using search_notes. Return 3-5 short factual bullets. Never write the final answer.",
    "writer": "ROLE: Writer\nWrite a clear answer (under 120 words) using ONLY the research provided. No new facts.",
    "critic": "ROLE: Critic\nReview the draft vs the research. Reply 'APPROVED' or 'ISSUES: ...' with concrete fixes.",
}


class Route(BaseModel):
    next: Literal["researcher", "writer", "critic", "FINISH"]
    reason: str = ""
    instruction: str = ""


@dataclass
class BoardEntry:
    worker: str
    instruction: str
    output: str


@dataclass
class TeamResult:
    answer: str
    board: list[BoardEntry]
    rounds: int
    stopped_reason: str  # finish | max_rounds | stuck


@dataclass
class SupervisorTeam:
    llm_factory: Callable[[str], LLM] = llm_for
    max_rounds: int = 8
    max_same_worker: int = 3
    verbose: bool | None = None
    board: list[BoardEntry] = field(default_factory=list)

    def __post_init__(self):
        tools = {"researcher": [search_notes]}
        self.workers = {
            w: Agent(self.llm_factory(w), tools.get(w, []), PROMPTS[w], name=w, max_steps=5,
                     tracer=Tracer(name=w, verbose=self.verbose))
            for w in WORKERS
        }
        self.supervisor_llm = self.llm_factory("supervisor")
        self.tracer = Tracer(name="supervisor", verbose=self.verbose)

    def _board_text(self) -> str:
        if not self.board:
            return "(nothing yet)"
        return "\n\n".join(f"[{e.worker}] (asked: {e.instruction})\n{e.output}" for e in self.board)

    def _worker_input(self, worker: str, question: str, instruction: str) -> str:
        """Private vs shared context: worker ko poora board nahi, sirf kaam ka hissa."""
        latest = {e.worker: e.output for e in self.board}  # har worker ka latest output
        parts = [f"USER QUESTION: {question}", f"YOUR INSTRUCTION: {instruction}"]
        if worker in ("writer", "critic") and "researcher" in latest:
            parts.append(f"RESEARCH:\n{latest['researcher']}")
        if worker == "writer" and "critic" in latest:
            parts.append(f"CRITIC FEEDBACK ON LAST DRAFT:\n{latest['critic']}")
        if worker == "critic" and "writer" in latest:
            parts.append(f"DRAFT:\n{latest['writer']}")
        return "\n\n".join(parts)

    def run(self, question: str) -> TeamResult:
        self.board = []
        streak, last_worker = 0, None
        for rnd in range(1, self.max_rounds + 1):
            route = llm_json(self.supervisor_llm, f"USER QUESTION: {question}\n\nWORK SO FAR:\n{self._board_text()}",
                             Route, system=PROMPTS["supervisor"])
            self.tracer.event("info", f"round {rnd}: -> {route.next} ({route.reason})")
            if route.next == "FINISH":
                return TeamResult(self._final(), self.board, rnd, "finish")
            streak = streak + 1 if route.next == last_worker else 1
            last_worker = route.next
            if streak > self.max_same_worker:  # stuck loop guard
                self.tracer.event("error", f"{route.next} picked {streak}x in a row, forcing finish")
                return TeamResult(self._final(), self.board, rnd, "stuck")
            out = self.workers[route.next].run(self._worker_input(route.next, question, route.instruction)).output
            self.board.append(BoardEntry(route.next, route.instruction, out))
        return TeamResult(self._final(), self.board, self.max_rounds, "max_rounds")

    def _final(self) -> str:
        drafts = [e.output for e in self.board if e.worker == "writer"]
        return drafts[-1] if drafts else "No answer was drafted."


# --------------------------------------------------------------------------- offline fake
def offline_llm() -> ScriptedLLM:
    """Fake jo realistic flow chalata hai: research -> write -> critic (issues) -> rewrite -> critic OK -> FINISH."""

    def respond(messages, tools):
        system = messages[0].content
        last = messages[-1]
        if "ROLE: Supervisor" in system:
            work = last.content.split("WORK SO FAR:", 1)[1]
            tags = [line.split("]")[0][1:] for line in work.splitlines() if line.startswith("[")]
            if not tags:
                return '{"next": "researcher", "reason": "need facts", "instruction": "Find facts about home solar panels"}'
            if tags[-1] == "researcher":
                return '{"next": "writer", "reason": "facts ready", "instruction": "Draft the answer"}'
            if tags[-1] == "writer":
                return '{"next": "critic", "reason": "review draft", "instruction": "Check accuracy"}'
            critic_out = work.rsplit("[critic]", 1)[1]
            if "APPROVED" in critic_out:
                return '{"next": "FINISH", "reason": "approved"}'
            return '{"next": "writer", "reason": "fix issues", "instruction": "Apply critic feedback"}'
        if "ROLE: Researcher" in system:
            if last.role == "tool":
                return "- Panels convert sunlight to electricity\n- Payback 6-10 years\n- Batteries store surplus"
            return tool_response(call("search_notes", query="solar"))
        if "ROLE: Writer" in system:
            if "CRITIC FEEDBACK" in last.content:
                return "Solar panels turn sunlight into electricity and usually pay for themselves in 6-10 years. Add a battery to use surplus power at night."
            return "Solar panels make electricity from sunlight and pay back in about 3 years."
        if "ROLE: Critic" in system:
            if "3 years" in last.content:
                return "ISSUES: payback is 6-10 years per research, not 3."
            return "APPROVED"
        return "?"

    return ScriptedLLM(respond)
