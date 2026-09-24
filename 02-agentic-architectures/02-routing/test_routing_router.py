import json

from routing_router import (complexity_score, handle_ticket, hybrid_route, llm_route, offline_handler_llm,
                            offline_router_llm, pick_model, rule_route)

from agentkit import ScriptedLLM


def test_rule_router_order_matters():
    assert rule_route("I want a refund, the payment went through twice").route == "refund"
    assert rule_route("invoice missing GST").route == "billing"
    assert rule_route("hello there") is None


def test_llm_router_structured_output():
    llm = ScriptedLLM([json.dumps({"route": "technical", "confidence": 0.8, "reason": "sync issue"})])
    d = llm_route(llm, "my files don't sync")
    assert d.route == "technical" and d.confidence == 0.8


def test_hybrid_skips_llm_when_rule_matches():
    llm = ScriptedLLM([])  # koi response nahi -> agar call hua to test fail
    r = hybrid_route(llm, "error 500 on login")
    assert r.method == "rule" and r.decision.route == "technical" and llm.calls == []


def test_hybrid_low_confidence_escalates():
    r = hybrid_route(offline_router_llm(), "something weird is happening")
    assert r.method == "llm" and r.needs_human


def test_hybrid_router_failure_is_safe():
    llm = ScriptedLLM(["not json"] * 3)
    r = hybrid_route(llm, "hmm")
    assert r.method == "fallback" and r.needs_human and r.decision.route == "general"


def test_model_routing():
    cheap, strong = offline_handler_llm("cheap"), offline_handler_llm("strong")
    assert pick_model("where is my invoice", cheap, strong) is cheap
    hard = "Explain why this fails? And compare options? ```Traceback```"
    assert complexity_score(hard) >= 2 and pick_model(hard, cheap, strong) is strong


def test_handler_uses_route_specific_prompt():
    cheap = offline_handler_llm("cheap")
    r = handle_ticket("I was charged twice", offline_router_llm(), cheap, offline_handler_llm("strong"))
    assert r.route == "billing" and not r.needs_human
    assert cheap.calls[0][0].content.startswith("You are a billing specialist")
