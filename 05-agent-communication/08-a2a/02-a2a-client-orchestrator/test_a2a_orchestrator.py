import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))

from agentkit import NullTracer, ScriptedLLM, call, tool_response  # noqa: E402

from a2a_client import A2AClient, A2AError, task_answer, task_data  # noqa: E402
from a2a_orchestrator import (AgentRegistry, SkillRouter, build_orchestrator_agent, delegate,  # noqa: E402
                              delegate_streaming, offline_orchestrator_llm)
from a2a_protocol import TaskState  # noqa: E402
from a2a_server_lib import build_a2a_app  # noqa: E402
from a2a_travel_agent import create_app, make_card, offline_llm  # noqa: E402

TRAVEL = "http://travel.test"
ECHO = "http://echo.test"


@pytest.fixture
def http():
    async def echo(ctx):
        yield ctx.status("completed", f"echo: {ctx.message.text()}", final=True)

    card = make_card(ECHO + "/").model_copy(update={"name": "Echo", "description": "Echoes text"})
    from a2a_protocol import AgentSkill

    card.skills = [AgentSkill(id="echo", name="Echo", description="Repeat text back", tags=["echo", "repeat"])]
    with TestClient(create_app(offline_llm(), url=TRAVEL + "/"), base_url=TRAVEL) as t, \
            TestClient(build_a2a_app(card, echo), base_url=ECHO) as e:
        yield {TRAVEL: t, ECHO: e}


def test_client_card_send_get_cancel(http):
    c = A2AClient(TRAVEL, http=http[TRAVEL])
    assert c.card.name == "Travel & Currency Expert"
    t = c.send("convert 100 USD to EUR")
    assert t.status.state == TaskState.completed
    assert task_data(t)["conversions"][0]["to"] == "EUR"
    assert c.get_task(t.id).id == t.id
    with pytest.raises(A2AError) as e:
        c.cancel(t.id)
    assert e.value.code == -32002


def test_registry_and_skill_router(http):
    reg = AgentRegistry([TRAVEL, ECHO], http=http)
    assert set(reg.agents) == {"Travel & Currency Expert", "Echo"}
    router = SkillRouter(reg)
    assert router.pick("convert money to INR currency") == ("Travel & Currency Expert", "currency-conversion")
    assert router.pick("please repeat this") == ("Echo", "echo")
    with pytest.raises(LookupError):
        router.pick("zzz qqq")


def test_delegate_handles_input_required(http):
    reg = AgentRegistry([TRAVEL], http=http)
    questions = []
    t = delegate(reg.get("Travel & Currency Expert"), "convert 20 USD",
                 ask_human=lambda q: questions.append(q) or "INR")
    assert t.status.state == TaskState.completed and "1660.0 INR" in task_answer(t)
    assert "Which currency" in questions[0]


def test_streaming_delegate(http):
    reg = AgentRegistry([TRAVEL], http=http)
    events = []
    final = delegate_streaming(reg.get("Travel & Currency Expert"), "tips for london", events.append)
    assert events[0].kind == "task" and events[-1].final
    assert "Tube" in task_answer(final)


def test_non_blocking_and_wait(http):
    c = A2AClient(TRAVEL, http=http[TRAVEL])
    t = c.send("tips for dubai", blocking=False)
    assert "Metro" in task_answer(c.wait(t.id, poll=0.01, timeout=5))


def test_llm_orchestrator_offline_brain_full_loop(http):
    reg = AgentRegistry([TRAVEL, ECHO], http=http)
    asked = []
    agent = build_orchestrator_agent(offline_orchestrator_llm(), reg, ask_human=lambda q: asked.append(q) or "GBP",
                                     tracer=NullTracer())
    res = agent.run("convert 40 EUR currency")
    assert asked and "Which currency" in asked[0]
    assert "GBP" in res.output and "2 agent(s)" in res.output
    tools_used = [m.name for m in res.messages if m.role == "tool"]
    assert tools_used == ["list_remote_agents", "send_to_agent", "ask_user", "send_to_agent"]


def test_orchestrator_with_scripted_llm_and_unknown_agent(http):
    reg = AgentRegistry([ECHO], http=http)
    llm = ScriptedLLM([tool_response(call("send_to_agent", agent_name="Nope", message="x")),
                       tool_response(call("send_to_agent", agent_name="Echo", message="hello")),
                       "Echo said hello."])
    res = build_orchestrator_agent(llm, reg, ask_human=lambda q: "", tracer=NullTracer()).run("say hello")
    tool_out = [m.content for m in res.messages if m.role == "tool"]
    assert "unknown agent" in tool_out[0]
    assert '"answer": "echo: hello"' in tool_out[1]


def test_token_required(http):
    with TestClient(create_app(offline_llm(), url="http://sec.test/", token="t0k"), base_url="http://sec.test") as s:
        with pytest.raises(A2AError) as e:
            A2AClient("http://sec.test", http=s).send("hi")
        assert e.value.code == 401
        assert A2AClient("http://sec.test", http=s, token="t0k").send("tips for goa").status.state == TaskState.completed
