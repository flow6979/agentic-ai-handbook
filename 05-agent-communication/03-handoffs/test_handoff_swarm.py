import copy

import pytest

import handoff_support
from agentkit import Message, ScriptedLLM, call, tool_response
from handoff_support import build_agents
from handoff_swarm import Swarm, SwarmAgent


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    monkeypatch.setattr(handoff_support, "INVOICES", copy.deepcopy(handoff_support.INVOICES))
    monkeypatch.setattr(handoff_support, "ACCOUNTS", copy.deepcopy(handoff_support.ACCOUNTS))


def test_triage_hands_off_to_billing_with_shared_history_and_context():
    llm = ScriptedLLM([
        tool_response(call("transfer_to_billing")),
        tool_response(call("refund_invoice", invoice_id="INV-2")),
        "Refunded.",
    ])
    res = Swarm(llm, build_agents()).run("charged twice", start="triage", context={"customer_id": "C-101"})
    assert res.handoff_path == ["triage", "billing"] and res.active_agent == "billing"
    assert handoff_support.INVOICES["C-101"][1]["status"] == "refunded"

    # 2nd LLM call billing ke system prompt ke saath hua, aur original user message usko dikha
    second = llm.calls[1]
    assert second[0].content.startswith("You are the billing agent")
    assert any(m.role == "user" and m.content == "charged twice" for m in second)
    # tools bhi badle: billing ke paas refund hai, triage ke paas nahi tha
    assert "Transferred to billing." in [m.content for m in second if m.role == "tool"]


def test_tools_offered_change_with_active_agent():
    seen = []

    def fake(messages, tools):
        seen.append(sorted(t.name for t in tools))
        return tool_response(call("transfer_to_tech")) if len(seen) == 1 else "ok"

    Swarm(ScriptedLLM(fake), build_agents()).run("locked out", start="triage", context={"customer_id": "C-101"})
    assert seen[0] == ["transfer_to_billing", "transfer_to_tech"]
    assert seen[1] == ["account_status", "transfer_to_triage", "unlock_account"]


def test_handback_and_multi_turn_continuation():
    llm = ScriptedLLM([
        tool_response(call("transfer_to_billing")), "Refund done.",
        tool_response(call("transfer_to_triage")), tool_response(call("transfer_to_tech")),
        tool_response(call("unlock_account")), "Unlocked.",
    ])
    swarm = Swarm(llm, build_agents())
    ctx = {"customer_id": "C-101"}
    r1 = swarm.run("double charge", start="triage", context=ctx)
    r2 = swarm.run("also locked", start=r1.active_agent, history=r1.messages, context=ctx)
    assert r2.handoff_path == ["billing", "triage", "tech"]
    assert handoff_support.ACCOUNTS["C-101"]["locked"] is False
    assert r2.messages[0].content == "double charge"  # history carry hui


def test_context_is_hidden_from_llm_schema():
    names = {t.name: t for t in build_agents()[1].tools}
    assert "context" not in names["refund_invoice"].parameters["properties"]
    assert names["refund_invoice"].parameters["required"] == ["invoice_id"]


def test_handoff_ping_pong_is_limited():
    a = SwarmAgent("a", "A.", handoffs=["b"])
    b = SwarmAgent("b", "B.", handoffs=["a"])

    def fake(messages, tools):
        name = messages[0].content.split()[3]
        return tool_response(call("transfer_to_b" if name == "a" else "transfer_to_a"))

    res = Swarm(ScriptedLLM(fake), [a, b], max_turns=10, max_handoffs=3).run("hi", start="a")
    assert len(res.handoff_path) == 4  # start + 3 handoffs, phir aur transfer reject
    assert any("too many transfers" in (m.content or "") for m in res.messages if m.role == "tool")
