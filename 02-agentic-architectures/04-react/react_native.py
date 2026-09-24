"""ReAct style (b): NATIVE function calling.

Yahan model khud structured `tool_calls` return karta hai (JSON, provider API level pe).
Koi text parsing nahi. Loop wahi ReAct hai (reason -> act -> observe), bas protocol
provider ka hai. agentkit.Agent exactly yahi loop hai.
"""
from __future__ import annotations

from agentkit import LLM, Agent, AgentResult, Tracer

from react_tools import TOOLS

NATIVE_SYSTEM = (
    "You answer questions using the available tools. Look facts up instead of guessing, "
    "use the calculator for arithmetic, and keep the final answer short."
)


def build_native_agent(llm: LLM, tracer: Tracer | None = None) -> Agent:
    return Agent(llm, TOOLS, NATIVE_SYSTEM, name="react-native", max_steps=8, tracer=tracer)


def run_react_native(llm: LLM, question: str, tracer: Tracer | None = None) -> AgentResult:
    return build_native_agent(llm, tracer).run(question)
