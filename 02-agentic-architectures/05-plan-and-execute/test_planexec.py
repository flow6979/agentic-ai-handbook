import json

import pytest

from agentkit import NullTracer, ScriptedLLM, call, tool_response
from planexec_agent import PlanAndExecute
from planexec_tools import TOOLS, calculator, get_weather

j = json.dumps


def test_tools():
    assert calculator.run({"expression": "2900 + 2*2800"}) == "8500"
    with pytest.raises(ValueError):
        calculator.run({"expression": "__import__('os')"})
    with pytest.raises(LookupError):
        get_weather.run({"city": "Atlantis"})


def test_happy_path_continue_then_finish():
    llm = ScriptedLLM([
        j({"steps": [{"description": "weather in Goa"}, {"description": "flights Delhi->Goa"}]}),
        tool_response(call("get_weather", city="Goa")), "sunny, 31C",
        j({"action": "continue"}),
        tool_response(call("search_flights", origin="Delhi", destination="Goa")), "IndiGo 5400",
        j({"action": "finish", "final_answer": "Go to Goa, IndiGo 5400 INR"}),
    ])
    res = PlanAndExecute(llm, TOOLS, tracer=NullTracer()).run("goa trip")
    assert res.answer == "Go to Goa, IndiGo 5400 INR"
    assert [h.failed for h in res.history] == [False, False]
    assert res.replans == 0


def test_failure_triggers_replan():
    llm = ScriptedLLM([
        j({"steps": [{"description": "flights Delhi->Kasol"}, {"description": "hotels Kasol"}]}),
        tool_response(call("search_flights", origin="Delhi", destination="Kasol")), "FAILED: no flights",
        j({"action": "replan", "new_steps": [{"description": "flights Delhi->Jaipur"}]}),
        tool_response(call("search_flights", origin="Delhi", destination="Jaipur")), "IndiGo 2900",
        j({"action": "finish", "final_answer": "Jaipur instead, 2900"}),
    ])
    res = PlanAndExecute(llm, TOOLS, tracer=NullTracer()).run("kasol trip")
    assert res.history[0].failed is True
    assert res.replans == 1
    assert res.plans[1] == ["flights Delhi->Jaipur"]
    # Executor ko tool error mila tha (crash nahi hua):
    tool_msgs = [m.content for msgs in llm.calls for m in msgs if m.role == "tool"]
    assert any("no flights from Delhi to Kasol" in t for t in tool_msgs)
    assert res.answer == "Jaipur instead, 2900"


def test_replan_budget():
    def script(msgs, tools):
        last = msgs[-1].content or ""
        if "Goal:" in last and "Done:" not in last:
            return j({"steps": [{"description": "impossible step"}]})
        if "Done:" in last:
            return j({"action": "replan", "new_steps": [{"description": "impossible step"}]})
        return "FAILED: cannot"

    res = PlanAndExecute(ScriptedLLM(script), TOOLS, max_replans=2, tracer=NullTracer()).run("x")
    assert res.replans == 2 and res.answer.startswith("Gave up")
