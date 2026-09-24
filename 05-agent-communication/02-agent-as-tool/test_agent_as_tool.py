import json

from agentkit import Agent, NullTracer, ScriptedLLM, call, tool_response

from agent_as_tool import agent_as_tool
from agent_as_tool_team import build_team, calculate


def test_manager_delegates_and_gets_structured_results():
    manager = ScriptedLLM([
        tool_response(call("ask_math_expert", task="pct change 950 -> 1200")),
        tool_response(call("ask_copywriter", task="post about 26.32% growth")),
        "done",
    ])
    math = ScriptedLLM([tool_response(call("percent_change", old=950, new=1200)), "26.32%"])
    writer = ScriptedLLM(['```json\n{"headline": "Up 26%", "body": "Nice"}\n```'])
    res = build_team(manager, math, writer, verbose=False).run("SECRET-ID-42: grow report please")

    tool_msgs = [json.loads(m.content) for m in res.messages if m.role == "tool"]
    assert tool_msgs[0] == {"agent": "math_expert", "ok": True, "output": "26.32%", "steps": 2,
                            "tokens": tool_msgs[0]["tokens"]}
    assert tool_msgs[1]["output"] == {"headline": "Up 26%", "body": "Nice"}  # JSON parsed

    # Context isolation: specialist ne manager ka user message kabhi nahi dekha
    for specialist in (math, writer):
        seen = " ".join(m.content or "" for call_msgs in specialist.calls for m in call_msgs)
        assert "SECRET-ID-42" not in seen
    # Specialist ko sirf task mila
    assert math.calls[0][-1].content == "pct change 950 -> 1200"


def test_subagent_failure_is_contained():
    looping = ScriptedLLM(lambda m, t: tool_response(call("calculate", expression="1+1")))
    sub = Agent(looping, [calculate], name="looper", max_steps=2, tracer=NullTracer())
    out = json.loads(agent_as_tool(sub, "ask_looper", "x").run({"task": "go"}))
    assert out["ok"] is False and out["steps"] == 2


def test_subagent_exception_is_contained():
    class Broken(ScriptedLLM):
        def chat(self, *a, **k):
            raise RuntimeError("provider down")

    sub = Agent(Broken([]), name="broken", tracer=NullTracer())
    out = json.loads(agent_as_tool(sub, "ask_broken", "x").run({"task": "go"}))
    assert out == {"agent": "broken", "ok": False, "error": "RuntimeError: provider down"}


def test_calculator_is_safe():
    assert calculate.run({"expression": "(1200-950)/950*100"}) == "26.3158"
    try:
        calculate.run({"expression": "__import__('os').system('ls')"})
        raise AssertionError("should have failed")
    except ValueError:
        pass
