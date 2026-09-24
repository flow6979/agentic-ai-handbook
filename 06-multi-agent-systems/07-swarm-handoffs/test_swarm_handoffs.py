from agentkit import ScriptedLLM, call, tool_response
from swarm_handoffs import SwarmAgent, Swarm, build_support_swarm, offline_llm


def swarm(fake=None, **kw):
    fake = fake or offline_llm()
    return Swarm(build_support_swarm(), llm_factory=lambda r: fake, verbose=False, **kw)


def test_triage_hands_off_to_refunds_and_refund_is_issued():
    ctx = {"customer_id": "C1"}
    res = swarm().run("I want a refund for order A100", start="triage", context=ctx)
    assert res.path == ["triage", "refunds"] and res.active_agent == "refunds"
    assert "Refund of INR 2999" in res.reply and ctx["refunds"] == ["A100"]


def test_context_variables_shared_and_visible_in_prompt():
    fake = offline_llm()
    ctx = {"customer_id": "C1"}
    swarm(fake).run("where is my order A200?", start="triage", context=ctx)
    assert ctx["order_id"] == "A200"
    assert "customer_id" in fake.calls[0][0].content  # CONTEXT injected into system prompt


def test_tech_path():
    res = swarm().run("my wifi router is not working", start="triage", context={})
    assert res.path == ["triage", "tech"] and "power-cycle" in res.reply


def test_handoff_not_in_allowed_list_is_rejected():
    agents = [SwarmAgent("a", "x", handoffs=[]), SwarmAgent("b", "y")]
    fake = ScriptedLLM([tool_response(call("transfer_to_b")), "stayed"])
    res = Swarm(agents, llm_factory=lambda r: fake, verbose=False).run("hi", start="a")
    assert res.path == ["a"] and res.reply == "stayed"
    assert "cannot hand off" in [m for m in res.messages if m.role == "tool"][0].content


def test_ping_pong_guard():
    agents = [SwarmAgent("a", "x", handoffs=["b"]), SwarmAgent("b", "y", handoffs=["a"])]

    def respond(messages, tools):
        me = messages[0].content.splitlines()[0][-1]
        return tool_response(call("transfer_to_" + ("b" if me == "a" else "a")))

    res = Swarm(agents, llm_factory=lambda r: ScriptedLLM(respond), max_handoffs=3, verbose=False).run("hi", start="a")
    assert res.stopped_reason == "max_handoffs" and len(res.path) == 5


def test_conversation_continues_with_active_agent():
    s = swarm()
    r1 = s.run("I want a refund for order A100", start="triage", context={})
    r2 = s.run("thanks, one more refund please", start=r1.active_agent, context=r1.context, history=r1.messages)
    assert r2.path == ["refunds"]  # triage skip, refunds agent hi continue karta hai
