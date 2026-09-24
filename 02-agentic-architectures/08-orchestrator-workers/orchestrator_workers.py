"""Orchestrator-Workers: orchestrator LLM RUNTIME pe decide karta hai ki kaunse subtasks chahiye,
workers ko dispatch karta hai, phir synthesizer sab jodta hai.

Parallelization (sectioning) se farak: wahan subtasks CODE mein fixed the (security/perf/readability).
Yahan subtasks INPUT pe depend karte hain -> orchestrator khud plan banata hai.

                          +--> worker(researcher): "competitor pricing" ---+
  goal --> [orchestrator] +--> worker(writer):     "landing page hero"  ---+--> [synthesizer] --> final
             (plan JSON)  +--> worker(analyst):    "launch risks"       ---+
                          (count aur types goal pe depend karte hain)

Guards: max_subtasks cap, unknown worker type -> 'generalist', dependency waves (depends_on),
worker failure isolated.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import BaseModel, Field

from agentkit import LLM, ScriptedLLM, llm_json

WORKERS: dict[str, str] = {
    "researcher": "You are a market researcher. Give concise, factual bullet points. Flag assumptions.",
    "writer": "You are a conversion copywriter. Write crisp, benefit-led copy.",
    "analyst": "You are a risk and metrics analyst. Be specific and quantitative where possible.",
    "engineer": "You are a senior software engineer. Give concrete technical steps.",
    "generalist": "You are a helpful expert. Do the task well and concisely.",
}


class Subtask(BaseModel):
    id: str
    worker: str = Field(description=f"one of: {', '.join(WORKERS)}")
    instruction: str
    depends_on: list[str] = Field(default_factory=list, description="ids whose output this task needs")


class Plan(BaseModel):
    subtasks: list[Subtask]


@dataclass
class WorkerResult:
    subtask: Subtask
    output: str
    ok: bool


@dataclass
class OrchestrationResult:
    plan: Plan
    results: list[WorkerResult]
    final: str


ORCH_SYSTEM = (
    "You are an orchestrator. Break the goal into the SMALLEST set of independent subtasks (2-6). "
    "Assign each to the best worker type. Use depends_on only when a task truly needs another's output."
)


def make_plan(llm: LLM, goal: str, max_subtasks: int) -> Plan:
    plan = llm_json(llm, f"Goal: {goal}\nWorker types: {list(WORKERS)}", Plan, system=ORCH_SYSTEM)
    plan.subtasks = plan.subtasks[:max_subtasks]  # runaway plan se bachao (cost cap)
    known = {s.id for s in plan.subtasks}
    for s in plan.subtasks:
        if s.worker not in WORKERS:
            s.worker = "generalist"
        s.depends_on = [d for d in s.depends_on if d in known and d != s.id]
    return plan


def waves(subtasks: list[Subtask]) -> list[list[Subtask]]:
    """Topological 'waves': har wave ke tasks parallel chal sakte hain. Cycle ho to error."""
    done: set[str] = set()
    remaining = list(subtasks)
    out = []
    while remaining:
        ready = [s for s in remaining if set(s.depends_on) <= done]
        if not ready:
            raise ValueError(f"dependency cycle among {[s.id for s in remaining]}")
        out.append(ready)
        done |= {s.id for s in ready}
        remaining = [s for s in remaining if s.id not in done]
    return out


def run_worker(llm: LLM, st: Subtask, goal: str, context: dict[str, str]) -> WorkerResult:
    ctx = "".join(f"\n\n[{d} output]\n{context[d]}" for d in st.depends_on if d in context)
    try:
        out = llm.complete(f"Overall goal: {goal}\nYour task: {st.instruction}{ctx}", system=WORKERS[st.worker])
        return WorkerResult(st, out, True)
    except Exception as e:
        return WorkerResult(st, f"(failed: {e})", False)


def synthesize(llm: LLM, goal: str, results: list[WorkerResult]) -> str:
    parts = "\n\n".join(f"### {r.subtask.id} ({r.subtask.worker}){'' if r.ok else ' [FAILED]'}\n{r.output}" for r in results)
    return llm.complete(
        f"Goal: {goal}\n\nWorker outputs:\n{parts}\n\nCombine into one coherent deliverable. Mention any failed parts.",
        system="You are an editor who merges team outputs into one polished document.",
    )


def orchestrate(orch_llm: LLM, worker_llm: LLM, goal: str, max_subtasks: int = 6, max_parallel: int = 4) -> OrchestrationResult:
    plan = make_plan(orch_llm, goal, max_subtasks)
    outputs: dict[str, str] = {}
    results: list[WorkerResult] = []
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        for wave in waves(plan.subtasks):
            for r in pool.map(lambda st: run_worker(worker_llm, st, goal, outputs), wave):
                results.append(r)
                outputs[r.subtask.id] = r.output
    return OrchestrationResult(plan, results, synthesize(orch_llm, goal, results))


# ---- Offline demo ------------------------------------------------------------------------------

DEMO_GOAL = "Prepare a launch kit for 'Snapdeploy', a 60-second GitHub-to-production deploy tool"


def offline_demo_llms() -> tuple[ScriptedLLM, ScriptedLLM]:
    plan = {"subtasks": [
        {"id": "pricing", "worker": "researcher", "instruction": "Summarise competitor pricing (Vercel, Render, Railway)."},
        {"id": "risks", "worker": "analyst", "instruction": "List top 3 launch risks with a metric to watch for each."},
        {"id": "hero", "worker": "writer", "instruction": "Write landing page hero copy using the pricing insight.",
         "depends_on": ["pricing"]},
    ]}
    orch = ScriptedLLM([json.dumps(plan), "# Snapdeploy Launch Kit\n(merged pricing, risks and hero copy)"])

    def worker(messages, tools):
        task = messages[-1].content
        if "competitor pricing" in task:
            return "- Vercel: free hobby, $20/user pro\n- Render: free tier, from $7/service\n- Railway: usage based"
        if "launch risks" in task:
            return "1. Cold starts (p95 deploy time)\n2. Abuse of free tier (signups/IP)\n3. GitHub API rate limits (429 rate)"
        if "hero copy" in task:
            assert "[pricing output]" in task, "writer should receive pricing context"
            return "Ship in 60 seconds. Free forever for side projects - cheaper than Render, simpler than Vercel."
        return "done"

    return orch, ScriptedLLM(worker)
