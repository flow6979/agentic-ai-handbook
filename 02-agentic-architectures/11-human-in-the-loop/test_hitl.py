import pytest

import hitl_tools
from agentkit import NullTracer, ScriptedLLM, call, tool_response
from hitl_agent import Decision, HITLAgent, RunState
from hitl_tools import POLICY, TOOLS


@pytest.fixture(autouse=True)
def reset_services():
    snapshot = {k: dict(v) for k, v in hitl_tools.SERVICES.items()}
    yield
    hitl_tools.SERVICES.clear()
    hitl_tools.SERVICES.update(snapshot)


def make(script, tmp_path):
    return HITLAgent(ScriptedLLM(script), TOOLS, POLICY, checkpoint_dir=tmp_path, tracer=NullTracer())


def test_safe_tools_run_without_pause(tmp_path):
    agent = make([tool_response(call("read_logs", service="checkout")), "pool exhausted"], tmp_path)
    st = agent.start("why slow?")
    assert st.status == "done" and st.output == "pool exhausted" and st.audit == []


def test_pause_checkpoint_resume_in_new_process(tmp_path):
    script = [tool_response(call("restart_service", service="checkout")), "restarted"]
    st = make(script, tmp_path).start("fix it")
    assert st.status == "waiting_approval" and st.awaiting.name == "restart_service"
    assert hitl_tools.SERVICES["checkout"]["status"] == "degraded"  # abhi chala NAHI

    # "Naya process": naya agent, state sirf file se
    loaded = HITLAgent.load(tmp_path / f"{st.run_id}.json")
    agent2 = HITLAgent(ScriptedLLM(["restarted"]), TOOLS, POLICY, checkpoint_dir=tmp_path, tracer=NullTracer())
    done = agent2.resume(loaded, Decision("approve", reviewer="alice"))
    assert done.status == "done" and hitl_tools.SERVICES["checkout"]["status"] == "healthy"
    assert done.audit[0]["reviewer"] == "alice" and done.audit[0]["action"] == "approve"


def test_edit_changes_args_everywhere(tmp_path):
    llm_script = [tool_response(call("scale_service", service="checkout", replicas=10)), "scaled"]
    agent = make(llm_script, tmp_path)
    st = RunState.from_json(agent.start("scale").to_json())  # round-trip bhi test
    done = agent.resume(st, Decision("edit", {"replicas": 4}))
    assert hitl_tools.SERVICES["checkout"]["replicas"] == 4
    assistant_call = [m for m in done.messages if m.tool_calls][0].tool_calls[0]
    assert assistant_call.arguments["replicas"] == 4  # history bhi consistent


def test_reject_tells_model(tmp_path):
    agent = make([tool_response(call("restart_service", service="checkout")), "ok, not restarting"], tmp_path)
    done = agent.resume(agent.start("fix"), Decision("reject", note="peak hours"))
    assert hitl_tools.SERVICES["checkout"]["status"] == "degraded"
    tool_msg = [m for m in done.messages if m.role == "tool"][0]
    assert "REJECTED" in tool_msg.content and "peak hours" in tool_msg.content


def test_forbidden_tool_escalates_never_runs(tmp_path):
    agent = make([tool_response(call("delete_database", database="prod")), "escalated it"], tmp_path)
    st = agent.start("clean up")
    assert st.status == "done" and st.escalations[0]["id"] == "ESC-1"
    assert "BLOCKED" in [m for m in st.messages if m.role == "tool"][0].content


def test_unknown_tool_defaults_to_approval(tmp_path):
    agent = make([tool_response(call("format_disk", path="/"))], tmp_path)
    assert agent.start("x").status == "waiting_approval"


def test_resume_when_not_waiting_raises(tmp_path):
    agent = make(["hi"], tmp_path)
    with pytest.raises(ValueError):
        agent.resume(agent.start("x"), Decision("approve"))
