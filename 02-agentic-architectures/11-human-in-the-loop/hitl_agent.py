"""Human-in-the-loop agent: approval gates, interrupt/resume (JSON checkpoint), edit, escalation.

agentkit.Agent ka `approve=` hook synchronous hai (process wahin ruk ke wait karta hai). Real
systems mein approval minutes/hours baad aata hai (Slack button, dashboard). Isliye yahan agent:

  1. risky tool call pe RUKTA hai  → status="waiting_approval"
  2. poora state JSON checkpoint mein SAVE karta hai  → process exit ho sakta hai
  3. baad mein kisi bhi process se RESUME hota hai with a Decision (approve / edit / reject)
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentkit import LLM, Message, NullTracer, Tool, ToolCall, Tracer

from hitl_tools import Risk

Status = Literal["running", "waiting_approval", "done", "failed"]


@dataclass
class Decision:
    action: Literal["approve", "reject", "edit"]
    edited_args: dict | None = None
    note: str = ""
    reviewer: str = "human"


@dataclass
class RunState:
    run_id: str
    task: str
    messages: list[Message]
    status: Status = "running"
    pending: list[ToolCall] = field(default_factory=list)  # model ne maange, abhi chale nahi
    steps: int = 0
    output: str | None = None
    escalations: list[dict] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)  # kisne kya approve kiya, kab (compliance!)

    @property
    def awaiting(self) -> ToolCall | None:
        return self.pending[0] if self.status == "waiting_approval" and self.pending else None

    # --- persistence ---------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2)

    @staticmethod
    def from_json(text: str) -> "RunState":
        d = json.loads(text)

        def msg(m: dict) -> Message:
            calls = [ToolCall(**c) for c in m.get("tool_calls") or []] or None
            return Message(**{**m, "tool_calls": calls})

        d["messages"] = [msg(m) for m in d["messages"]]
        d["pending"] = [ToolCall(**c) for c in d["pending"]]
        return RunState(**d)


class HITLAgent:
    def __init__(self, llm: LLM, tools: list[Tool], policy: dict[str, Risk], *, system_prompt: str = "",
                 checkpoint_dir: str | Path | None = None, max_steps: int = 10, tracer: Tracer | None = None):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.policy = policy
        self.system_prompt = system_prompt or (
            "You are an on-call DevOps assistant. Investigate with read-only tools first. Some actions need "
            "human approval or are forbidden; if a tool result says REJECTED or BLOCKED, adapt and tell the user."
        )
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.max_steps = max_steps
        self.tracer = tracer or NullTracer(name="hitl")

    # --- public API ------------------------------------------------------------
    def start(self, task: str) -> RunState:
        state = RunState(run_id=uuid.uuid4().hex[:8], task=task,
                         messages=[Message.system(self.system_prompt), Message.user(task)])
        return self._loop(state)

    def resume(self, state: RunState, decision: Decision) -> RunState:
        call = state.awaiting
        if call is None:
            raise ValueError(f"run {state.run_id} is not waiting for approval (status={state.status})")
        state.audit.append({"ts": time.time(), "tool": call.name, "args": call.arguments, **dataclasses.asdict(decision)})
        self.tracer.event("info", f"human decision: {decision.action} {decision.edited_args or ''} {decision.note}")

        if decision.action == "reject":
            state.pending.pop(0)
            self._append_result(state, call, f"REJECTED by {decision.reviewer}: {decision.note or 'no reason given'}")
        else:
            if decision.action == "edit":
                self._edit_call(state, call, decision.edited_args or {})
            state.pending.pop(0)
            self._append_result(state, call, self._execute(call))
        state.status = "running"
        return self._loop(state)

    def save(self, state: RunState) -> Path | None:
        if not self.checkpoint_dir:
            return None
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / f"{state.run_id}.json"
        path.write_text(state.to_json())
        return path

    @staticmethod
    def load(path: str | Path) -> RunState:
        return RunState.from_json(Path(path).read_text())

    # --- internals -------------------------------------------------------------
    def _execute(self, call: ToolCall) -> str:
        tool = self.tools.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool {call.name!r}"
        try:
            return tool.run(call.arguments)
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"

    def _append_result(self, state: RunState, call: ToolCall, result: str) -> None:
        self.tracer.event("tool", f"{call.name}({call.arguments}) -> {result}")
        state.messages.append(Message.tool(call, result))

    @staticmethod
    def _edit_call(state: RunState, call: ToolCall, new_args: dict) -> None:
        """Human ne args badle: pending call AUR history ke assistant message dono update karo,
        taaki model ko consistent history dikhe (usne jo 'maanga' woh wahi hai jo chala)."""
        call.arguments = {**call.arguments, **new_args}
        for m in reversed(state.messages):
            for c in m.tool_calls or []:
                if c.id == call.id:
                    c.arguments = dict(call.arguments)
                    return

    def _drain_pending(self, state: RunState) -> bool:
        """Pending calls chalao. Approval chahiye to False return (ruk jao)."""
        while state.pending:
            call = state.pending[0]
            risk = self.policy.get(call.name, Risk.NEEDS_APPROVAL)  # unknown tool = default-deny-ish
            if risk is Risk.FORBIDDEN:
                ticket = {"id": f"ESC-{len(state.escalations) + 1}", "tool": call.name, "args": call.arguments}
                state.escalations.append(ticket)
                state.pending.pop(0)
                self.tracer.event("error", f"ESCALATED {ticket}")
                self._append_result(state, call, f"BLOCKED: '{call.name}' is forbidden for the agent. "
                                                 f"Escalated to the on-call engineer as ticket {ticket['id']}.")
                continue
            if risk is Risk.NEEDS_APPROVAL:
                state.status = "waiting_approval"
                self.tracer.event("info", f"PAUSED: approval needed for {call.name}({call.arguments})")
                return False
            state.pending.pop(0)
            self._append_result(state, call, self._execute(call))
        return True

    def _loop(self, state: RunState) -> RunState:
        while True:
            if not self._drain_pending(state):
                self.save(state)
                return state
            if state.steps >= self.max_steps:
                state.status, state.output = "failed", "Step limit reached."
                self.save(state)
                return state
            resp = self.llm.chat(state.messages, [t.spec for t in self.tools.values()])
            state.steps += 1
            state.messages.append(Message.assistant(resp.content, resp.tool_calls or None))
            if not resp.tool_calls:
                state.status, state.output = "done", resp.content or ""
                self.tracer.event("result", state.output)
                self.save(state)
                return state
            state.pending = list(resp.tool_calls)
            self.save(state)  # har LLM step ke baad checkpoint: crash ho to bhi resume ho sake
