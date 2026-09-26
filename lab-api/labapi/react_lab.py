"""ReAct lab: 02-agentic-architectures/04-react ko UI se chalao.

params:
    mode: "text" | "native"
    question: str
    max_steps: int                 (Tinker: 2 karke max_steps guard dekho)
    calculator_docstring: bool     (Tinker: False = tool description hata do)
    lookup_fails_first: bool       (Tinker: pehli lookup call error de)

UI events (type="step"): thought, action, observation, tool_call, tool_result, answer, format_error
"""
from __future__ import annotations

import dataclasses

from agentkit import Agent, ScriptedLLM, Tool, call, tool_response

from .registry import Lab
from .runtime import LabContext, meter, use_project

PROJECT = "02-agentic-architectures/04-react"
DEFAULT_Q = "How many times taller is Mount Everest than the Eiffel Tower?"


def _offline_llm(mode: str) -> ScriptedLLM:
    if mode == "text":
        return ScriptedLLM([
            'Thought: I need the height of Mount Everest.\nAction: lookup\nAction Input: {"query": "mount everest height"}',
            'Thought: Now I need the height of the Eiffel Tower.\nAction: lookup\nAction Input: {"query": "eiffel tower height"}',
            'Thought: Divide the two heights.\nAction: calculator\nAction Input: {"expression": "8849 / 330"}',
            "Thought: I now know the final answer\nFinal Answer: Mount Everest (8849 m) is about 26.8 times taller than the Eiffel Tower (330 m).",
        ])
    return ScriptedLLM([
        tool_response(call("lookup", query="mount everest height"), call("lookup", query="eiffel tower height")),
        tool_response(call("calculator", expression="8849 / 330")),
        "Mount Everest (8849 m) is about 26.8 times taller than the Eiffel Tower (330 m).",
    ])


def _tools(ctx: LabContext) -> list[Tool]:
    import react_tools

    tools = list(react_tools.TOOLS)
    if ctx.params.get("calculator_docstring") is False:
        tools = [dataclasses.replace(t, description="x") if t.name == "calculator" else t for t in tools]
    if ctx.params.get("lookup_fails_first"):
        orig = next(t for t in tools if t.name == "lookup")
        state = {"n": 0}

        def flaky(**kw):
            state["n"] += 1
            if state["n"] == 1:
                raise TimeoutError("knowledge base did not respond (simulated)")
            return orig.fn(**kw)

        tools = [dataclasses.replace(t, fn=flaky) if t.name == "lookup" else t for t in tools]
    return tools


def _text_events(ctx: LabContext):
    def on(ev):
        msg, kind = ev.get("message", ""), ev.get("kind")
        if kind == "llm" and msg.startswith("Thought:"):
            ctx.step("thought", msg[len("Thought:"):].strip())
        elif kind == "tool" and msg.startswith("Observation:"):
            ctx.step("observation", msg[len("Observation:"):].strip())
        elif kind == "tool":
            ctx.step("action", msg)
        elif kind == "error":
            ctx.step("format_error", msg)
        elif kind == "result":
            ctx.step("answer", msg)
    return on


def _native_events(ctx: LabContext):
    def on(ev):
        msg, kind = ev.get("message", ""), ev.get("kind")
        if kind == "tool":
            ctx.step("tool_call", msg)
        elif msg.startswith("-> "):
            ctx.step("tool_result", msg[3:], error=kind == "error")
        elif kind == "llm" and msg.startswith("thought: "):
            ctx.step("thought", msg[len("thought: "):])
        elif kind == "result":
            ctx.step("answer", msg)
        elif kind == "error":
            ctx.step("stopped", msg)
    return on


def run(ctx: LabContext) -> dict:
    use_project(PROJECT)
    import react_native
    import react_textloop
    from agentkit import NullTracer

    mode = ctx.params.get("mode", "text")
    question = (ctx.params.get("question") or DEFAULT_Q).strip()
    max_steps = int(ctx.params.get("max_steps", 8))
    llm = meter(_offline_llm(mode), ctx.emit) if ctx.offline else ctx.llm()
    tools = _tools(ctx)

    if mode == "text":
        tracer = NullTracer(name="react-text", on_event=_text_events(ctx))
        res = react_textloop.run_react_text(llm, tools, question, max_steps=max_steps, tracer=tracer)
        answer, stopped, steps = res.answer, res.stopped_reason, len(res.steps)
        if stopped == "max_steps":
            ctx.step("stopped", answer)
    else:
        tracer = NullTracer(name="react-native", on_event=_native_events(ctx))
        agent = Agent(llm, tools, react_native.NATIVE_SYSTEM, name="react-native", max_steps=max_steps, tracer=tracer)
        res = agent.run(question)
        answer, stopped, steps = res.output, res.stopped_reason, res.steps

    return {"answer": answer, "stopped_reason": stopped, "steps": steps, "mode": mode, "question": question,
            "offline": ctx.offline, **llm.stats()}


LAB = Lab(id="react", project=PROJECT, run=run,
          defaults={"mode": "text", "question": DEFAULT_Q, "max_steps": 8})
