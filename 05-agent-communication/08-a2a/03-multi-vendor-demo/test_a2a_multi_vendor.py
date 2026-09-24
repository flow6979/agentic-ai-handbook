import os
import socket
import sys
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "01-a2a-server"))
sys.path.insert(0, os.path.join(HERE, "..", "02-a2a-client-orchestrator"))

from agentkit import NullTracer, ScriptedLLM  # noqa: E402

from a2a_client import A2AClient, A2AError, task_data  # noqa: E402
from a2a_orchestrator import AgentRegistry, build_orchestrator_agent, offline_orchestrator_llm  # noqa: E402
from a2a_packing_agent_raw import create_packing_app, parse_request  # noqa: E402
from a2a_protocol import AgentCard, Task, TaskState  # noqa: E402
from a2a_travel_agent import create_app, offline_llm  # noqa: E402
from a2a_trip_planner import TripRequest, plan_trip  # noqa: E402

T, P = "http://travel.local", "http://packing.local"


@pytest.fixture
def http():
    with TestClient(create_app(offline_llm(), url=T + "/"), base_url=T) as t, \
            TestClient(create_packing_app(P + "/"), base_url=P) as p:
        yield {T: t, P: p}


def test_raw_agent_is_spec_shaped(http):
    """Hand-written server ke outputs hamare pydantic models se validate hone chahiye = wire compatible."""
    card = AgentCard.model_validate(http[P].get("/.well-known/agent.json").json())
    assert card.capabilities.streaming is False
    c = A2AClient(P, http=http[P])
    task = c.send("pack for goa in july for 4 days")
    assert isinstance(task, Task) and task.status.state == TaskState.completed
    data = task_data(task)
    assert data["climate"] == "rainy" and "umbrella" in data["items"] and "4 sets of clothes" in data["items"]
    assert c.get_task(task.id).id == task.id


def test_client_respects_streaming_capability(http):
    with pytest.raises(A2AError) as e:
        list(A2AClient(P, http=http[P]).stream("pack for paris"))
    assert e.value.code == -32004


def test_parse_request_prefers_data_part():
    assert parse_request([{"kind": "text", "text": "tokyo"}, {"kind": "data", "data": {"city": "Paris", "month": 12, "days": 2}}]) \
        == {"city": "Paris", "month": 12, "days": 2}


def test_plan_trip_fans_out_to_both_vendors(http):
    reg = AgentRegistry([T, P], http=http)
    plan = plan_trip(reg, TripRequest("Tokyo", 1, 5, 500, "USD", "JPY"))
    assert "Suica" in plan.tips
    assert "500.0 USD = 75000.0 JPY" in plan.budget_line
    assert plan.climate == "cold" and "warm jacket" in plan.packing
    assert "Packing Assistant (Another Vendor Inc.)" == plan.agents_used["packing"]
    assert plan.agents_used["tips"].startswith("Travel & Currency Expert")


def test_plan_trip_with_llm_summary(http):
    reg = AgentRegistry([T, P], http=http)
    plan = plan_trip(reg, TripRequest("Paris", 7, 3, 100, "EUR", "EUR"), summarizer=ScriptedLLM(["Have a great trip!"]))
    assert plan.render().startswith("Have a great trip!")


def test_llm_orchestrator_picks_packing_vendor(http):
    reg = AgentRegistry([T, P], http=http)
    res = build_orchestrator_agent(offline_orchestrator_llm(), reg, ask_human=lambda q: "", tracer=NullTracer()) \
        .run("what should I pack for my london trip in december for 3 days")
    sent = [m.tool_calls[0].arguments for m in res.messages if m.role == "assistant" and m.tool_calls
            and m.tool_calls[0].name == "send_to_agent"]
    assert sent[0]["agent_name"] == "Packing Assistant"
    assert "thermal layers" in res.output


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(app, port):
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    while not srv.started:
        time.sleep(0.02)
    return srv, th


def test_over_real_network():
    """Asli HTTP ports: dono servers alag 'machines' jaise; card.url sahi port batata hai."""
    pt, pp = _free_port(), _free_port()
    servers = [_serve(create_app(offline_llm(), f"http://127.0.0.1:{pt}/"), pt),
               _serve(create_packing_app(f"http://127.0.0.1:{pp}/"), pp)]
    try:
        reg = AgentRegistry([f"http://127.0.0.1:{pt}", f"http://127.0.0.1:{pp}"])
        plan = plan_trip(reg, TripRequest("Dubai", 7, 2, 100, "USD", "AED"))
        assert "367.0 AED" in plan.budget_line and plan.climate == "hot"
    finally:
        for srv, th in servers:
            srv.should_exit = True
            th.join(5)
