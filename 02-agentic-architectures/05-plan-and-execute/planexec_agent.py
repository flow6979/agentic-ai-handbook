"""Plan-and-Execute agent.

    goal ──► PLANNER (llm_json → Plan) ──► EXECUTOR (har step ek chhota ReAct agent)
                     ▲                              │ step result
                     └──────── REPLANNER ◄──────────┘
                     (continue | replan | finish)

Planner ek baar poora plan banata hai (big picture). Executor ek-ek step karta hai (sirf
current step pe focus, chhota context). Replanner har step ke baad decide karta hai: plan
theek chal raha hai, badalna hai, ya kaam ho gaya.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from agentkit import LLM, Agent, NullTracer, Tool, Tracer, llm_json


class Step(BaseModel):
    description: str = Field(description="One concrete action, e.g. 'Check weather in Goa'")


class Plan(BaseModel):
    steps: list[Step]


class ReplanDecision(BaseModel):
    action: Literal["continue", "replan", "finish"]
    reason: str = ""
    new_steps: list[Step] = Field(default_factory=list, description="Only for replan: the remaining steps")
    final_answer: str | None = Field(default=None, description="Only for finish")


@dataclass
class StepRecord:
    step: str
    result: str
    failed: bool


@dataclass
class PlanExecResult:
    answer: str
    history: list[StepRecord] = field(default_factory=list)
    plans: list[list[str]] = field(default_factory=list)  # har (re)plan ka snapshot
    replans: int = 0


PLANNER_SYSTEM = (
    "You are a planner. Break the user's goal into 2-6 short, concrete steps. "
    "Each step should be doable with ONE of these tools: {tools}. Do not execute anything."
)
EXECUTOR_SYSTEM = (
    "You execute ONE step of a larger plan using tools. Do only this step. "
    "If a tool fails or the step is impossible, reply starting with 'FAILED:' and say why. "
    "Otherwise reply with the concrete result (numbers, names)."
)
REPLANNER_SYSTEM = (
    "You supervise a plan. Given the goal, the steps done (with results) and the steps remaining, decide:\n"
    "- 'continue' if the remaining plan still makes sense,\n"
    "- 'replan' if a step failed or results change what should happen next (give new_steps for the REST),\n"
    "- 'finish' if the goal is achieved (give final_answer to the user)."
)


class PlanAndExecute:
    def __init__(self, llm: LLM, tools: list[Tool], *, max_steps: int = 10, max_replans: int = 3,
                 tracer: Tracer | None = None):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.tracer = tracer or NullTracer(name="plan-exec")

    def plan(self, goal: str) -> list[str]:
        names = ", ".join(t.name for t in self.tools)
        p = llm_json(self.llm, f"Goal: {goal}", Plan, system=PLANNER_SYSTEM.format(tools=names))
        return [s.description for s in p.steps]

    def execute_step(self, goal: str, step: str, history: list[StepRecord]) -> StepRecord:
        context = "\n".join(f"- {h.step} => {h.result}" for h in history) or "(nothing yet)"
        executor = Agent(self.llm, self.tools, EXECUTOR_SYSTEM, name="executor", max_steps=4, tracer=self.tracer)
        out = executor.run(f"Overall goal: {goal}\nResults so far:\n{context}\n\nYOUR STEP: {step}").output
        failed = out.strip().upper().startswith("FAILED")
        return StepRecord(step, out, failed)

    def replan(self, goal: str, history: list[StepRecord], remaining: list[str]) -> ReplanDecision:
        done = "\n".join(f"{i + 1}. {h.step} => {'FAILED ' if h.failed else ''}{h.result}" for i, h in enumerate(history))
        rest = "\n".join(f"- {s}" for s in remaining) or "(none)"
        prompt = f"Goal: {goal}\n\nDone:\n{done}\n\nRemaining:\n{rest}"
        return llm_json(self.llm, prompt, ReplanDecision, system=REPLANNER_SYSTEM)

    def run(self, goal: str) -> PlanExecResult:
        remaining = self.plan(goal)
        result = PlanExecResult(answer="", plans=[list(remaining)])
        self.tracer.event("info", "PLAN: " + " | ".join(remaining))

        for _ in range(self.max_steps):
            if not remaining:
                break
            step = remaining.pop(0)
            rec = self.execute_step(goal, step, result.history)
            result.history.append(rec)
            self.tracer.event("error" if rec.failed else "result", f"STEP '{step}' => {rec.result}")

            decision = self.replan(goal, result.history, remaining)
            self.tracer.event("info", f"REPLANNER: {decision.action} ({decision.reason})")
            if decision.action == "finish":
                result.answer = decision.final_answer or rec.result
                return result
            if decision.action == "replan":
                if result.replans >= self.max_replans:
                    result.answer = "Gave up: too many replans. Last result: " + rec.result
                    return result
                result.replans += 1
                remaining = [s.description for s in decision.new_steps]
                result.plans.append(list(remaining))
                self.tracer.event("info", "NEW PLAN: " + " | ".join(remaining))

        # Steps khatam ya budget khatam: jo mila usse answer
        result.answer = result.answer or "Plan ended without an explicit finish. Results: " + "; ".join(
            h.result for h in result.history)
        return result
