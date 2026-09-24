from spectrum_demo import offline_agent_llm, offline_chain_llm, run_as_agent, run_as_chain


def test_chain_does_math_in_code_and_calls_llm_once():
    llm = offline_chain_llm()
    out = run_as_chain(llm, "u1")
    assert out.total == {"subtotal": 4097.0, "tax": 737.46, "total": 4834.46}
    assert len(llm.calls) == 1
    # numbers LLM ko prompt mein diye gaye (LLM ne calculate nahi kiye)
    assert "4834.46" in llm.calls[0][-1].content


def test_agent_decides_tool_order_itself():
    llm = offline_agent_llm()
    res = run_as_agent(llm, "cart total for u1?")
    tool_names = [m.name for m in res.messages if m.role == "tool"]
    assert tool_names == ["get_cart", "compute_total"]
    assert '"total": 4834.46' in [m.content for m in res.messages if m.role == "tool"][1]
    assert res.steps == 3  # agent = more LLM calls than the chain


def test_agent_recovers_from_bad_user_id():
    from agentkit import ScriptedLLM, call, tool_response

    llm = ScriptedLLM([tool_response(call("get_cart", user_id="nope")), "Sorry, I couldn't find that cart."])
    res = run_as_agent(llm, "cart for nope")
    assert "ERROR" in [m.content for m in res.messages if m.role == "tool"][0]
    assert "couldn't find" in res.output
