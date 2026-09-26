"""Multi-agent lab: 06-multi-agent-systems ke 4 topologies UI se chalao.

params:
    topology:   "supervisor" | "crew" | "groupchat" | "swarm"
    task:       str (khaali = topology ka default task)
    max_rounds: int (supervisor rounds / group chat turns / swarm steps)
    selector:   "llm" | "rules" | "roundrobin"   (sirf groupchat)
    models:     {role: "provider:model"}         (har role ka apna LLM; ctx.llm(role) isse padhta hai)

Project code bilkul wahi hai (supervisor_team.py, sequential_crew.py, group_chat.py, swarm_handoffs.py).
Hum sirf do cheezein lapet-te (wrap) hain taaki UI live dekh sake:
  1. har role ka LLM ek "spy" mein: call se pehle `agent_active` event, supervisor ka JSON `route` event
  2. project ke Tracer ko hamare tracer se badalte hain: tool calls, handoffs, messages events ban jaate hain

UI events (type="step"): agent_active, round, route, message, handoff, tool, tool_result, done
"""
from __future__ import annotations

import re
from typing import Any, Callable

from agentkit import LLM, LLMResponse, NullTracer, extract_json

from .registry import Lab
from .runtime import LabContext, MeteredLLM, meter, use_project

BASE = "06-multi-agent-systems"
PROJECTS = {
    "supervisor": f"{BASE}/03-supervisor-team",
    "crew": f"{BASE}/02-sequential-crew",
    "groupchat": f"{BASE}/05-group-chat",
    "swarm": f"{BASE}/07-swarm-handoffs",
}
DEFAULT_TASKS = {
    "supervisor": "Should I install solar panels at home? Give a short, accurate answer.",
    "crew": "a tiny calculator library that adds two numbers",
    "groupchat": "Plan 3 days in Goa under INR 30k",
    "swarm": "I want a refund for order A100",
}
ROLES = {
    "supervisor": ["supervisor", "researcher", "writer", "critic"],
    "crew": ["pm", "architect", "developer", "qa"],
    "groupchat": ["manager", "planner", "budget_keeper", "local_guide"],
    "swarm": ["triage", "orders", "refunds", "tech"],
}


class _Spy(LLM):
    """Role ka LLM: har call se pehle UI ko batao kaun bol raha hai."""

    def __init__(self, inner: LLM, ctx: LabContext, role: str, on_response: Callable[[LLMResponse], None] | None = None):
        self.inner, self.ctx, self.role, self.on_response = inner, ctx, role, on_response
        self.provider, self.model = inner.provider, inner.model

    def chat(self, messages, tools=None, **kw) -> LLMResponse:
        self.ctx.step("agent_active", self.role, role=self.role)
        resp = self.inner.chat(messages, tools, **kw)
        if self.on_response:
            self.on_response(resp)
        return resp


class _Factory:
    """llm_factory(role) jo project classes maangti hain. Har role ka ek metered LLM (cache)."""

    def __init__(self, ctx: LabContext, offline_llm: LLM | None, hooks: dict[str, Callable] | None = None):
        self.ctx, self.offline_llm, self.hooks = ctx, offline_llm, hooks or {}
        self.metered: dict[str, MeteredLLM] = {}

    def __call__(self, role: str) -> LLM:
        if role not in self.metered:
            base = meter(self.offline_llm, self.ctx.emit, role) if self.offline_llm else self.ctx.llm(role)
            self.metered[role] = base
        return _Spy(self.metered[role], self.ctx, role, self.hooks.get(role))

    def stats(self) -> dict[str, Any]:
        tot = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "ms": 0}
        for m in self.metered.values():
            for k, v in m.stats().items():
                tot[k] += v
        return tot


def _worker_tracer(ctx: LabContext, role: str, reply_to: str | None):
    """agentkit Agent ke tracer events -> UI events."""

    def on(ev: dict[str, Any]) -> None:
        kind, msg = ev.get("kind"), ev.get("message", "")
        if kind == "tool":
            ctx.step("tool", msg, role=role)
        elif msg.startswith("-> "):
            ctx.step("tool_result", msg[3:], role=role, error=kind == "error")
        elif kind == "result" and reply_to:
            ctx.step("message", msg, sender=role, receiver=reply_to)

    return NullTracer(name=role, on_event=on)


# --------------------------------------------------------------------------- supervisor
def _supervisor(ctx: LabContext, task: str, max_rounds: int) -> dict[str, Any]:
    import supervisor_team as st

    rounds = {"n": 0}

    def on_route(resp: LLMResponse) -> None:
        try:
            route = st.Route.model_validate(extract_json(resp.content or ""))
        except Exception:  # llm_json khud retry karega; hum sirf valid routes dikhate hain
            return
        rounds["n"] += 1
        ctx.step("round", f"{rounds['n']}/{max_rounds}", n=rounds["n"], max=max_rounds)
        ctx.step("route", route.model_dump_json(), next=route.next, reason=route.reason, instruction=route.instruction)
        if route.next != "FINISH":
            ctx.step("message", route.instruction or route.reason, sender="supervisor", receiver=route.next)

    factory = _Factory(ctx, st.offline_llm() if ctx.offline else None, {"supervisor": on_route})
    team = st.SupervisorTeam(llm_factory=factory, max_rounds=max_rounds, verbose=False)
    for w, agent in team.workers.items():
        agent.tracer = _worker_tracer(ctx, w, "supervisor")
    res = team.run(task)
    return {"answer": res.answer, "stopped_reason": res.stopped_reason, "rounds": res.rounds,
            "board": [{"worker": e.worker, "instruction": e.instruction, "output": e.output} for e in res.board],
            **factory.stats()}


# --------------------------------------------------------------------------- sequential crew
def _crew(ctx: LabContext, task: str) -> dict[str, Any]:
    import sequential_crew as sc

    nxt = {"pm": "architect", "architect": "developer", "developer": "qa"}

    class LabCrew(sc.SoftwareCrew):
        step_n = 0

        def _agent(self, role):
            agent = super()._agent(role)
            agent.tracer = _worker_tracer(ctx, role.key, nxt.get(role.key))
            self.step_n += 1
            ctx.step("round", f"task {self.step_n}", n=self.step_n, max=4 + 2 * self.max_reworks)
            return agent

        def _review(self, outputs):
            self.step_n += 1
            ctx.step("round", f"task {self.step_n}", n=self.step_n, max=4 + 2 * self.max_reworks)
            verdict = super()._review(outputs)
            to = "user" if verdict.passed else "developer"
            ctx.step("message", verdict.model_dump_json(), sender="qa", receiver=to)
            return verdict

    factory = _Factory(ctx, sc.offline_llm() if ctx.offline else None)
    crew = LabCrew(llm_factory=factory, max_reworks=1, verbose=False)
    res = crew.kickoff(task)
    answer = "\n\n".join(f"# {p}\n{c}" for p, c in res.files.items()) or res.outputs.get("code", "")
    return {"answer": answer, "stopped_reason": "qa_passed" if res.qa.passed else "qa_failed", "rounds": crew.step_n,
            "reworks": res.reworks, "files": res.files, "qa": res.qa.model_dump(),
            "outputs": {k: v for k, v in res.outputs.items() if k != "qa"}, **factory.stats()}


# --------------------------------------------------------------------------- group chat
def _groupchat(ctx: LabContext, task: str, max_rounds: int, selector: str) -> dict[str, Any]:
    import group_chat as gc

    factory = _Factory(ctx, gc.offline_llm() if ctx.offline else None)
    sel = {"llm": lambda: gc.LLMSelector(factory("manager")),
           "rules": lambda: gc.RuleBasedSelector(gc.TRIP_RULES),
           "roundrobin": gc.RoundRobinSelector}.get(selector, lambda: gc.LLMSelector(factory("manager")))()
    chat = gc.GroupChat(gc.trip_team(factory), sel, max_turns=max_rounds, verbose=False)

    def on(ev: dict[str, Any]) -> None:
        if ev.get("kind") == "llm":
            speaker, _, text = ev.get("message", "").partition(": ")
            n = ev.get("turn", 0)
            ctx.step("round", f"{n}/{max_rounds}", n=n, max=max_rounds)
            ctx.step("message", text, sender=speaker, receiver="all")

    chat.tracer = NullTracer(name="groupchat", on_event=on)
    ctx.step("message", task, sender="user", receiver="all")
    res = chat.run(task)
    last = res.transcript[-1]
    return {"answer": f"{last.speaker}: {last.content}", "stopped_reason": res.stopped_reason, "rounds": res.turns,
            "selector": selector, "transcript": [{"speaker": m.speaker, "content": m.content} for m in res.transcript],
            **factory.stats()}


# --------------------------------------------------------------------------- swarm
_HANDOFF = re.compile(r"^(\w+) -> (\w+) \((.*)\)$", re.S)
_TOOL = re.compile(r"^\[(\w+)\] (.*)$", re.S)


def _swarm(ctx: LabContext, task: str, max_rounds: int) -> dict[str, Any]:
    import swarm_handoffs as sh

    steps = {"n": 0}
    base_factory = _Factory(ctx, sh.offline_llm() if ctx.offline else None)

    def factory(role: str) -> LLM:
        llm = base_factory(role)
        inner_chat = llm.chat

        def chat(messages, tools=None, **kw):
            steps["n"] += 1
            ctx.step("round", f"step {steps['n']}", n=steps["n"], max=max_rounds)
            return inner_chat(messages, tools, **kw)

        llm.chat = chat  # type: ignore[method-assign]
        return llm

    swarm = sh.Swarm(sh.build_support_swarm(), llm_factory=factory, max_steps=max_rounds)

    def on(ev: dict[str, Any]) -> None:
        msg = ev.get("message", "")
        if m := _HANDOFF.match(msg):
            ctx.step("handoff", m.group(3), sender=m.group(1), receiver=m.group(2))
        elif m := _TOOL.match(msg):
            ctx.step("tool", m.group(2), role=m.group(1))

    swarm.tracer = NullTracer(name="swarm", on_event=on)
    ctx.step("message", task, sender="user", receiver="triage")
    res = swarm.run(task, start="triage", context={"customer_id": "C1"})
    ctx.step("message", res.reply, sender=res.active_agent, receiver="user")
    return {"answer": res.reply, "stopped_reason": res.stopped_reason, "rounds": steps["n"], "path": res.path,
            "context": res.context, **base_factory.stats()}


def run(ctx: LabContext) -> dict:
    topology = ctx.params.get("topology", "supervisor")
    if topology not in PROJECTS:
        raise ValueError(f"unknown topology {topology!r}")
    use_project(PROJECTS[topology])
    task = (ctx.params.get("task") or DEFAULT_TASKS[topology]).strip()
    max_rounds = int(ctx.params.get("max_rounds") or (12 if topology == "swarm" else 8))

    if topology == "supervisor":
        out = _supervisor(ctx, task, max_rounds)
    elif topology == "crew":
        out = _crew(ctx, task)
    elif topology == "groupchat":
        out = _groupchat(ctx, task, max_rounds, ctx.params.get("selector", "llm"))
    else:
        out = _swarm(ctx, task, max_rounds)
    ctx.step("done", out["answer"], reason=out["stopped_reason"])
    return {"topology": topology, "task": task, "roles": ROLES[topology], "steps": out["rounds"],
            "offline": ctx.offline, **out}


LAB = Lab(
    id="multi",
    project=BASE,
    run=run,
    defaults={"topology": "supervisor", "max_rounds": 8, "selector": "llm"},
    smoke_cases=[{"topology": "supervisor"}, {"topology": "crew"}, {"topology": "groupchat"},
                 {"topology": "groupchat", "selector": "rules"}, {"topology": "swarm"}],
)
