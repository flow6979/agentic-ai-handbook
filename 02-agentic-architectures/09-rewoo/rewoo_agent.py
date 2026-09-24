"""ReWOO: Reasoning WithOut Observation (Xu et al., 2023).

ReAct: LLM → tool → LLM → tool → LLM ...   (har tool ke baad poora context dobara LLM ko)
ReWOO: PLANNER (1 LLM call, saare tool calls + #E variables)
       → WORKERS (tools chalao, koi LLM nahi, #E substitute karo)
       → SOLVER (1 LLM call, plan + evidence se answer)

Planner output example:
    Plan: Find the height of Everest.
    #E1 = lookup[mount everest height in metres]
    Plan: Find the height of the Eiffel Tower.
    #E2 = lookup[eiffel tower height in metres]
    Plan: Divide them.
    #E3 = calculator[#E1 / #E2]
"""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agentkit import LLM, Message, NullTracer, Tool, Tracer, Usage

PLANNER_PROMPT = """For the task below, make a plan that solves it step by step. For each step write one
'Plan:' line and then exactly one evidence line '#E<n> = <tool>[<input>]'. Inputs may reference earlier
evidence like #E1. Do NOT solve the task yourself, only plan.

Tools:
{tools}
- LLM[input]: ask a language model to reason over or extract something from text (can reference #E).

Task: {task}"""

SOLVER_PROMPT = """Solve the task using the plan and the evidence collected for each step.
Evidence can be wrong or contain ERRORs; use it carefully. Answer concisely.

{plan_with_evidence}

Task: {task}
Answer:"""

_STEP = re.compile(r"^\s*(#E\d+)\s*=\s*([A-Za-z_]\w*)\s*\[(.*)\]\s*$")
_REF = re.compile(r"#E\d+")


@dataclass
class PlanStep:
    var: str  # "#E1"
    tool: str
    tool_input: str
    reason: str = ""
    evidence: str | None = None

    @property
    def deps(self) -> set[str]:
        return set(_REF.findall(self.tool_input))


@dataclass
class ReWOOResult:
    answer: str
    steps: list[PlanStep] = field(default_factory=list)
    levels: list[list[str]] = field(default_factory=list)
    llm_calls: int = 0
    usage: Usage = field(default_factory=Usage)


def parse_plan(text: str, tool_names: set[str]) -> list[PlanStep]:
    steps: list[PlanStep] = []
    reason = ""
    seen: set[str] = set()
    for line in text.splitlines():
        if line.strip().lower().startswith("plan:"):
            reason = line.split(":", 1)[1].strip()
            continue
        m = _STEP.match(line)
        if not m:
            continue
        var, tool_name, tool_input = m.groups()
        if tool_name not in tool_names:
            raise ValueError(f"plan uses unknown tool {tool_name!r}")
        step = PlanStep(var, tool_name, tool_input.strip(), reason)
        missing = step.deps - seen
        if missing:
            raise ValueError(f"{var} references {sorted(missing)} before they are defined")
        seen.add(var)
        steps.append(step)
    if not steps:
        raise ValueError("planner produced no '#E = tool[input]' lines")
    return steps


def dependency_levels(steps: list[PlanStep]) -> list[list[PlanStep]]:
    """Steps ko 'levels' mein baanto: ek level ke steps ek doosre pe depend nahi karte → parallel chal sakte hain."""
    level_of: dict[str, int] = {}
    for s in steps:
        level_of[s.var] = 1 + max((level_of[d] for d in s.deps), default=-1)
    levels: list[list[PlanStep]] = [[] for _ in range(max(level_of.values()) + 1)]
    for s in steps:
        levels[level_of[s.var]].append(s)
    return levels


class ReWOO:
    def __init__(self, llm: LLM, tools: list[Tool], *, tracer: Tracer | None = None, parallel: bool = True):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.tracer = tracer or NullTracer(name="rewoo")
        self.parallel = parallel
        self._lock = threading.Lock()  # LLM workers parallel threads mein counters update karte hain

    def _call_llm(self, prompt: str, result: ReWOOResult) -> str:
        resp = self.llm.chat([Message.user(prompt)])
        with self._lock:
            result.llm_calls += 1
            result.usage = result.usage + resp.usage
        return resp.content or ""

    def _work(self, step: PlanStep, evidence: dict[str, str], result: ReWOOResult) -> str:
        filled = _REF.sub(lambda m: evidence.get(m.group(0), m.group(0)), step.tool_input)
        try:
            if step.tool == "LLM":
                return self._call_llm(filled, result).strip()
            tool = self.tools[step.tool]
            param = next(iter(tool.parameters["properties"]))  # sab workers single-input hain
            return tool.run({param: filled})
        except Exception as e:  # error bhi evidence hai; solver decide karega
            return f"ERROR: {type(e).__name__}: {e}"

    def run(self, task: str) -> ReWOOResult:
        result = ReWOOResult(answer="")
        tool_desc = "\n".join(f"- {n}[input]: {t.description}" for n, t in self.tools.items())
        plan_text = self._call_llm(PLANNER_PROMPT.format(tools=tool_desc, task=task), result)
        steps = parse_plan(plan_text, set(self.tools) | {"LLM"})
        result.steps = steps
        self.tracer.event("info", "PLAN:\n" + "\n".join(f"{s.var} = {s.tool}[{s.tool_input}]" for s in steps))

        evidence: dict[str, str] = {}
        levels = dependency_levels(steps)
        result.levels = [[s.var for s in lvl] for lvl in levels]
        for lvl in levels:
            if self.parallel and len(lvl) > 1:
                with ThreadPoolExecutor(max_workers=len(lvl)) as pool:
                    outs = list(pool.map(lambda s: self._work(s, evidence, result), lvl))
            else:
                outs = [self._work(s, evidence, result) for s in lvl]
            for s, out in zip(lvl, outs):
                s.evidence = evidence[s.var] = out
                self.tracer.event("tool", f"{s.var} = {s.tool}[{s.tool_input}] -> {out}")

        pwe = "\n".join(f"Plan: {s.reason}\n{s.var} = {s.tool}[{s.tool_input}]\nEvidence: {s.evidence}" for s in steps)
        result.answer = self._call_llm(SOLVER_PROMPT.format(plan_with_evidence=pwe, task=task), result).strip()
        self.tracer.event("result", result.answer)
        return result
