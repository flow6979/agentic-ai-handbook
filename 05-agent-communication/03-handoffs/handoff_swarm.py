"""Handoffs: control ek agent se dusre agent ko transfer karna (call-center transfer jaisa).

OpenAI Swarm / Agents SDK wala pattern:
- Har agent ke paas apne tools + kuch `transfer_to_<name>` tools hote hain.
- LLM jab `transfer_to_billing` call karta hai, runner ACTIVE agent badal deta hai.
- Conversation history SHARED rehti hai: naya agent pichli saari baat dekhta hai.
- Sirf system prompt aur tools badalte hain (naye agent ke).
- `context` dict (customer_id wagairah) tools ko milta hai, LLM ko nahi.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from agentkit import LLM, Message, NullTracer, Tracer
from agentkit.tools import Tool

TRANSFER_PREFIX = "transfer_to_"


@dataclass
class SwarmAgent:
    name: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)  # kin agents ko transfer kar sakta hai

    def transfer_tool(self, target: str, description: str) -> Tool:
        return Tool(
            name=f"{TRANSFER_PREFIX}{target}",
            description=f"Hand the conversation to the {target} agent. {description}",
            parameters={"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
            fn=lambda **_: f"Transferred to {target}.",
        )


@dataclass
class SwarmResult:
    output: str
    active_agent: str
    messages: list[Message]
    handoff_path: list[str]
    context: dict[str, Any]


class Swarm:
    def __init__(self, llm: LLM, agents: list[SwarmAgent], *, max_turns: int = 12, max_handoffs: int = 4,
                 tracer: Tracer | None = None):
        self.llm = llm
        self.agents = {a.name: a for a in agents}
        self.max_turns = max_turns
        self.max_handoffs = max_handoffs  # triage <-> billing ping-pong se bachao
        self.tracer = tracer or NullTracer("swarm")

    def _tools_for(self, agent: SwarmAgent) -> dict[str, Tool]:
        tools = {t.name: t for t in agent.tools}
        for target in agent.handoffs:
            desc = self.agents[target].instructions.split(".")[0]
            t = agent.transfer_tool(target, desc)
            tools[t.name] = t
        return tools

    @staticmethod
    def _call(tool: Tool, args: dict, context: dict) -> str:
        # Agar tool function `context` parameter maangta hai to inject karo (LLM ko dikhta nahi)
        if "context" in inspect.signature(tool.fn).parameters:
            args = {**args, "context": context}
        try:
            return tool.run(args)
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"

    def run(self, user_input: str, *, start: str, history: list[Message] | None = None,
            context: dict[str, Any] | None = None) -> SwarmResult:
        context = dict(context or {})
        active = self.agents[start]
        messages = [*(history or []), Message.user(user_input)]  # shared history (bina system)
        path, handoffs = [active.name], 0

        for _ in range(self.max_turns):
            tools = self._tools_for(active)
            # Har turn pe system prompt ACTIVE agent ka
            system = Message.system(f"You are the {active.name} agent. {active.instructions}")
            resp = self.llm.chat([system, *messages], [t.spec for t in tools.values()] or None)
            messages.append(Message.assistant(resp.content, resp.tool_calls or None))
            if not resp.tool_calls:
                self.tracer.event("result", f"{active.name}: {resp.content}")
                return SwarmResult(resp.content or "", active.name, messages, path, context)

            next_agent = None
            for c in resp.tool_calls:
                tool = tools.get(c.name)
                if tool is None:
                    result = f"ERROR: {active.name} has no tool {c.name!r}"
                elif c.name.startswith(TRANSFER_PREFIX):
                    target = c.name[len(TRANSFER_PREFIX):]
                    if handoffs >= self.max_handoffs:
                        result = "ERROR: too many transfers; answer the user yourself."
                    else:
                        result, next_agent = tool.run({}), self.agents[target]
                else:
                    result = self._call(tool, c.arguments, context)
                self.tracer.event("tool", f"{active.name}.{c.name}({c.arguments}) -> {result}")
                messages.append(Message.tool(c, result))
            if next_agent:
                handoffs += 1
                self.tracer.event("info", f"HANDOFF {active.name} -> {next_agent.name}")
                active = next_agent
                path.append(active.name)

        return SwarmResult("Sorry, I could not resolve this.", active.name, messages, path, context)
