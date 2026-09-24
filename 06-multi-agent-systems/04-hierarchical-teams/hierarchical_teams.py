"""Hierarchical teams: manager of managers.

                         +-------------------+
                         |   Launch Manager  |   (goal -> team objectives)
                         +---------+---------+
                  +----------------+----------------+
                  v                                 v
        +------------------+              +--------------------+
        | Marketing Lead   |              | Engineering Lead   |   (objective -> worker tasks)
        +--------+---------+              +---------+----------+
          +------+------+                    +------+------+
          v             v                    v             v
     copywriter   social_media          backend_dev   qa_engineer    (actual kaam)

Results neeche se upar 'roll up' hote hain: workers -> lead ka team report -> manager ka final plan.
Har level sirf apne direct reports se baat karta hai -> har LLM call ka context chhota rehta hai.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from agentkit import LLM, Agent, ScriptedLLM, Tracer, get_llm, llm_json


def llm_for(role: str) -> LLM:
    spec = os.getenv(f"LLM_MODEL_{role.upper()}")
    return get_llm(spec) if spec else get_llm()


# --------------------------------------------------------------------------- org chart
TEAMS: dict[str, dict[str, str]] = {
    "marketing": {
        "copywriter": "ROLE: Copywriter\nWrite punchy product copy (headline + 2 lines). Nothing else.",
        "social_media": "ROLE: Social Media Specialist\nWrite 2 short launch posts (X and LinkedIn). Nothing else.",
    },
    "engineering": {
        "backend_dev": "ROLE: Backend Developer\nList the concrete backend work items (max 4 bullets) for the objective.",
        "qa_engineer": "ROLE: QA Engineer\nList the launch test checklist (max 4 bullets) for the objective.",
    },
}

MANAGER_PROMPT = (
    "ROLE: Launch Manager\nYou split a product launch goal into one objective per team. "
    f"Teams available: {', '.join(TEAMS)}. Only use these team names."
)


def lead_prompt(team: str) -> str:
    return (f"ROLE: {team.title()} Lead\nYou lead the {team} team with workers: {', '.join(TEAMS[team])}. "
            "Split your objective into one task per worker (only those names).")


class Assignment(BaseModel):
    team: str
    objective: str


class LaunchPlan(BaseModel):
    assignments: list[Assignment]


class WorkerTask(BaseModel):
    worker: str
    task: str


class TeamPlan(BaseModel):
    tasks: list[WorkerTask]


@dataclass
class TeamReport:
    team: str
    objective: str
    worker_outputs: dict[str, str]
    summary: str


@dataclass
class LaunchResult:
    plan: LaunchPlan
    reports: list[TeamReport]
    final: str
    skipped: list[str] = field(default_factory=list)  # invalid team/worker names jo LLM ne invent kiye


class TeamLead:
    def __init__(self, team: str, llm_factory: Callable[[str], LLM], verbose: bool | None = None):
        self.team, self.llm_factory, self.verbose = team, llm_factory, verbose
        self.llm = llm_factory(f"{team}_lead")

    def execute(self, objective: str, skipped: list[str]) -> TeamReport:
        plan = llm_json(self.llm, f"OBJECTIVE: {objective}", TeamPlan, system=lead_prompt(self.team))
        outputs: dict[str, str] = {}
        for t in plan.tasks:
            if t.worker not in TEAMS[self.team]:  # hallucinated worker -> skip, crash nahi
                skipped.append(f"{self.team}/{t.worker}")
                continue
            worker = Agent(self.llm_factory(t.worker), [], TEAMS[self.team][t.worker], name=t.worker,
                           tracer=Tracer(name=f"{self.team}.{t.worker}", verbose=self.verbose))
            outputs[t.worker] = worker.run(f"TEAM OBJECTIVE: {objective}\nYOUR TASK: {t.task}").output
        # Roll-up #1: lead apni team ka result summarise karta hai (manager ko raw outputs nahi jaate)
        body = "\n\n".join(f"[{w}]\n{o}" for w, o in outputs.items())
        summary = self.llm.complete(f"OBJECTIVE: {objective}\n\nWORKER OUTPUTS:\n{body}\n\nWrite a 3-line team report.",
                                    system=lead_prompt(self.team))
        return TeamReport(self.team, objective, outputs, summary)


class LaunchManager:
    def __init__(self, llm_factory: Callable[[str], LLM] = llm_for, verbose: bool | None = None):
        self.llm_factory, self.verbose = llm_factory, verbose
        self.llm = llm_factory("manager")

    def run(self, goal: str) -> LaunchResult:
        plan = llm_json(self.llm, f"LAUNCH GOAL: {goal}", LaunchPlan, system=MANAGER_PROMPT)
        reports, skipped = [], []
        for a in plan.assignments:
            if a.team not in TEAMS:
                skipped.append(a.team)
                continue
            reports.append(TeamLead(a.team, self.llm_factory, self.verbose).execute(a.objective, skipped))
        # Roll-up #2: manager sirf team summaries dekhta hai
        body = "\n\n".join(f"[{r.team}] {r.summary}" for r in reports)
        final = self.llm.complete(f"LAUNCH GOAL: {goal}\n\nTEAM REPORTS:\n{body}\n\nWrite the final launch plan (5 lines).",
                                  system=MANAGER_PROMPT)
        return LaunchResult(plan, reports, final, skipped)


# --------------------------------------------------------------------------- offline fake
def offline_llm(invent_bad_names: bool = False) -> ScriptedLLM:
    def respond(messages, tools):
        system, last = messages[0].content, messages[-1].content
        if "ROLE: Launch Manager" in system:
            if "TEAM REPORTS" in last:
                return "Launch plan: 1) finish API 2) QA checklist 3) publish copy 4) post socials 5) monitor."
            teams = [{"team": "marketing", "objective": "Create launch messaging"},
                     {"team": "engineering", "objective": "Ship v1 API reliably"}]
            if invent_bad_names:
                teams.append({"team": "legal", "objective": "review"})
            return json.dumps({"assignments": teams})
        if "ROLE: Marketing Lead" in system:
            if "WORKER OUTPUTS" in last:
                return "Marketing: copy + 2 posts ready."
            extra = [{"worker": "designer", "task": "logo"}] if invent_bad_names else []
            return json.dumps({"tasks": [{"worker": "copywriter", "task": "headline"},
                                         {"worker": "social_media", "task": "launch posts"}] + extra})
        if "ROLE: Engineering Lead" in system:
            if "WORKER OUTPUTS" in last:
                return "Engineering: 4 backend items, QA checklist ready."
            return '{"tasks": [{"worker": "backend_dev", "task": "API work"}, {"worker": "qa_engineer", "task": "checklist"}]}'
        role = system.splitlines()[0]
        return f"output of {role}"

    return ScriptedLLM(respond)
