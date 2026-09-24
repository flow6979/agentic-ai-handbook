"""Trip planner: do alag 'vendors' ke A2A agents ko parallel mein use karke ek plan banao.

    Travel & Currency Expert  (agentkit + LLM provider A, streaming haan)
    Packing Assistant         (raw FastAPI, koi LLM nahi, streaming nahi)
    Orchestrator              (tumhara code; optional LLM provider B se final summary)

                   ┌──► Travel agent:  "tips for tokyo"          ─┐
    plan_trip() ───┼──► Travel agent:  "convert 500 USD to JPY"   ├──► combine ──► (LLM summary)
                   └──► Packing agent: DataPart{city,month,days} ─┘
    (ThreadPool = teeno requests ek saath; A2A calls independent HTTP hain)
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))
sys.path.insert(0, os.path.join(HERE, "..", "02-a2a-client-orchestrator"))

from agentkit import LLM  # noqa: E402

from a2a_client import task_answer, task_data  # noqa: E402
from a2a_orchestrator import AgentRegistry, SkillRouter  # noqa: E402


@dataclass
class TripRequest:
    city: str
    month: int
    days: int
    budget: float
    home_currency: str
    local_currency: str


@dataclass
class TripPlan:
    tips: str
    budget_line: str
    packing: list[str]
    climate: str
    agents_used: dict[str, str]  # sub-task -> agent name (+ provider org)
    summary: str | None = None

    def render(self) -> str:
        lines = [f"Budget: {self.budget_line}", f"Tips: {self.tips}",
                 f"Climate: {self.climate}", "Pack: " + ", ".join(self.packing), "",
                 "Agents used:"] + [f"  - {k}: {v}" for k, v in self.agents_used.items()]
        if self.summary:
            lines = [self.summary, ""] + lines
        return "\n".join(lines)


def plan_trip(registry: AgentRegistry, req: TripRequest, *, summarizer: LLM | None = None) -> TripPlan:
    router = SkillRouter(registry)
    jobs = {
        "tips": (router.pick("travel tips city trip")[0], dict(text=f"tips for {req.city}")),
        "budget": (router.pick("convert currency money")[0],
                   dict(text=f"convert {req.budget} {req.home_currency} to {req.local_currency}")),
        # structured input: DataPart, taaki dusra agent parse na kare, seedha padhe
        "packing": (router.pick("packing luggage clothes")[0],
                    dict(text=f"packing list for {req.city}", data={"city": req.city, "month": req.month, "days": req.days})),
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {k: pool.submit(registry.get(name).client.send, **kw) for k, (name, kw) in jobs.items()}
        results = {k: f.result() for k, f in futures.items()}

    packing = task_data(results["packing"])
    used = {}
    for k, (name, _) in jobs.items():
        org = registry.get(name).card.provider.organization if registry.get(name).card.provider else "?"
        used[k] = f"{name} ({org})"
    plan = TripPlan(tips=task_answer(results["tips"]), budget_line=task_answer(results["budget"]),
                    packing=packing.get("items", []), climate=packing.get("climate", "?"), agents_used=used)
    if summarizer is not None:
        plan.summary = summarizer.complete(
            "Write a friendly 3-sentence trip brief from these facts:\n" + plan.render(),
            system="You summarise travel plans. Use only the given facts.")
    return plan
