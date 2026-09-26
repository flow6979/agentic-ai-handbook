import json

from labapi import run


def go(params):
    events = []
    out = run({"lab": "support", "params": params, "offline": True}, events.append)
    json.dumps(events, default=str)
    json.dumps(out, default=str)
    assert out["ok"], out
    return out["result"], [e for e in events if e["type"] == "step"]


def kinds(steps):
    return [s["kind"] for s in steps]


def test_order_lookup_runs_full_pipeline():
    r, steps = go({"message": "Where is my order ORD-1001?", "reset": True})
    assert r["status"] == "ok" and "BlueDart" in r["answer"]
    k = kinds(steps)
    for expected in ["request", "guardrail", "intent", "tool", "policy", "tool_result", "answer", "observability"]:
        assert expected in k, (expected, k)
    obs = r["observability"]
    assert obs["request_id"].startswith("req_") and obs["rate_limit_remaining"] == obs["rate_limit"] - 1
    assert obs["fallback_chain"][0]["status"] == "ok"


def test_prompt_injection_blocked_before_llm():
    r, steps = go({"simulate": "injection", "reset": True})
    assert r["status"] == "refused" and r["error_code"] == "prompt_injection"
    assert r["llm_calls"] == 0  # guard ne LLM tak pahunchne hi nahi diya
    g = [s for s in steps if s["kind"] == "guardrail"][0]
    assert g["ok"] is False and g["reason"] == "prompt_injection"


def test_pii_is_redacted_in_log_event():
    _, steps = go({"message": "My card 4111 1111 1111 1111 and email x@y.com, where is ORD-1001?", "reset": True})
    req = steps[0]
    assert req["pii_redacted"] and "[CARD]" in req["redacted"] and "[EMAIL]" in req["redacted"]


def test_big_refund_pauses_then_approve_resumes():
    r, steps = go({"message": "I want a refund for ORD-1002", "reset": True})
    assert r["status"] == "needs_approval" and r["pending"]["amount"] == 129.0
    assert "approval_needed" in kinds(steps)
    sid = r["session_id"]
    r2, steps2 = go({"session_id": sid, "approval": "approve"})
    assert r2["status"] == "ok" and "129.00" in r2["answer"]
    assert r2["refunds"][0]["approved_by"] == "human"
    assert any(s["kind"] == "policy" and s["approved"] for s in steps2)


def test_reject_escalates():
    r, _ = go({"message": "I want a refund for ORD-1002", "reset": True})
    r2, _ = go({"session_id": r["session_id"], "approval": "reject"})
    assert r2["status"] == "ok" and "human agent" in r2["answer"] and r2["refunds"] == []


def test_edit_amount_partial_refund():
    r, _ = go({"message": "I want a refund for ORD-1002", "reset": True})
    r2, _ = go({"session_id": r["session_id"], "approval": {"edit": {"amount": 60}}})
    assert r2["refunds"][0]["amount"] == 60 and "60.00" in r2["answer"]


def test_auto_limit_auto_approves():
    r, steps = go({"message": "I want a refund for ORD-1002", "auto_limit": 500, "reset": True})
    assert r["status"] == "ok" and r["refunds"][0]["approved_by"] == "auto-policy"


def test_resume_without_pending_is_error():
    events = []
    out = run({"lab": "support", "params": {"session_id": "nope", "approval": "approve"}, "offline": True}, events.append)
    assert not out["ok"]
