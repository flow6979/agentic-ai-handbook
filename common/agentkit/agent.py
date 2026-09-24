"""Agent loop: LLM + tools + loop. Har agent ka dil yahi hai.

    while steps < max_steps:
        response = llm.chat(messages, tools)
        if response mein tool calls hain:
            har tool chalao, result messages mein daalo
        else:
            final answer return karo

Production guards jo is loop mein hain:
- max_steps: infinite loop se bachao (model baar baar tool chalata rahe)
- tool errors model ko wapas bhejo (crash nahi) taaki woh khud fix kare
- unknown tool / tooti JSON args -> error message, crash nahi
- token usage count, har step trace
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .llm import LLM, Message, Usage
from .tools import Tool
from .tracing import Tracer


@dataclass
class AgentResult:
    output: str
    messages: list[Message]
    steps: int
    usage: Usage = field(default_factory=Usage)
    stopped_reason: str = "final_answer"  # final_answer | max_steps


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[Tool] | None = None,
        system_prompt: str = "You are a helpful assistant.",
        *,
        name: str = "agent",
        max_steps: int = 10,
        tracer: Tracer | None = None,
        approve: Callable[[str, dict], bool] | None = None,
    ):
        self.llm = llm
        self.tools = {t.name: t for t in (tools or [])}
        self.system_prompt = system_prompt
        self.name = name
        self.max_steps = max_steps
        self.tracer = tracer or Tracer(name=name)
        self.approve = approve  # human-in-the-loop hook: risky tool se pehle poochho

    def _run_tool(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool {name!r}. Available: {sorted(self.tools)}"
        if "_raw" in args:
            return f"ERROR: arguments were not valid JSON: {args['_raw']!r}"
        if self.approve and not self.approve(name, args):
            return "ERROR: a human rejected this tool call. Try something else or explain."
        try:
            return tool.run(args)
        except Exception as e:  # tool fail hua -> model ko batao, woh retry/alternate karega
            return f"ERROR: {type(e).__name__}: {e}"

    def run(self, user_input: str, history: list[Message] | None = None) -> AgentResult:
        messages = [Message.system(self.system_prompt), *(history or []), Message.user(user_input)]
        usage = Usage()
        specs = [t.spec for t in self.tools.values()] or None
        self.tracer.event("info", f"task: {user_input}")

        for step in range(1, self.max_steps + 1):
            resp = self.llm.chat(messages, specs)
            usage = usage + resp.usage
            messages.append(Message.assistant(resp.content, resp.tool_calls or None))

            if not resp.tool_calls:
                self.tracer.event("result", resp.content or "", step=step, tokens=usage.__dict__)
                return AgentResult(resp.content or "", messages, step, usage)

            if resp.content:
                self.tracer.event("llm", f"thought: {resp.content}", step=step)
            for c in resp.tool_calls:
                self.tracer.event("tool", f"{c.name}({c.arguments})", step=step)
                result = self._run_tool(c.name, c.arguments)
                self.tracer.event("error" if result.startswith("ERROR") else "llm", f"-> {result}", step=step)
                messages.append(Message.tool(c, result))

        self.tracer.event("error", f"stopped: max_steps={self.max_steps} reached")
        return AgentResult("I could not finish within the step limit.", messages, self.max_steps, usage, "max_steps")
