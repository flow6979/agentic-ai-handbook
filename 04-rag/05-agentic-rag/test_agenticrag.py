import json

import pytest

from agentkit import NullTracer, ScriptedLLM, call, get_embedder, tool_response
from agenticrag_core import NOT_FOUND, CorrectiveRAG, build_rag_agent, default_kbs, make_search_tool, offline_agentic_llm


@pytest.fixture(scope="module")
def kbs():
    return default_kbs(get_embedder("local"))


def test_search_tool_schema_and_results(kbs):
    t = make_search_tool(kbs["hr"])
    assert t.name == "search_hr" and t.parameters["required"] == ["query"]
    assert "leave_policy.md" in t.run({"query": "sick leave days"})


def test_routes_to_single_kb(kbs):
    r = CorrectiveRAG(ScriptedLLM(offline_agentic_llm), kbs).run("How many sick leave days do employees get?")
    assert r.route == ["hr"] and "12 days" in r.answer and r.grounded is True


def test_multi_part_question_decomposed_across_kbs(kbs):
    r = CorrectiveRAG(ScriptedLLM(offline_agentic_llm), kbs).run(
        "What is the refund window and how many sick leave days do employees get?")
    assert set(r.route) == {"hr", "product"} and len(r.sub_questions) == 2
    assert {p.source for p in r.passages} >= {"refund_policy.md", "leave_policy.md"}


def test_no_retrieval_for_chitchat(kbs):
    llm = ScriptedLLM(offline_agentic_llm)
    r = CorrectiveRAG(llm, kbs).run("hello there")
    assert r.route == [] and r.passages == []
    assert len(llm.calls) == 2  # route + direct reply, koi retrieval/grade nahi


def test_rewrite_rescues_vocabulary_mismatch(kbs):
    r = CorrectiveRAG(ScriptedLLM(offline_agentic_llm), kbs).run("How many vacation days do I get?")
    assert any(t.startswith("rewrite ->") for t in r.trace)
    assert r.passages and r.passages[0].source == "leave_policy.md"


def test_not_found_when_grader_rejects_everything(kbs):
    script = [
        json.dumps({"kbs": ["hr"], "reason": "x"}),
        json.dumps({"questions": ["Can I bring my dog to office?"]}),
        json.dumps({"relevant": []}),
        json.dumps({"query": "pets policy office"}),
        json.dumps({"relevant": []}),
    ]
    r = CorrectiveRAG(ScriptedLLM(script), kbs).run("Can I bring my dog to office?")
    assert r.answer == NOT_FOUND


def test_ungrounded_answer_is_regenerated_then_flagged(kbs):
    script = [
        json.dumps({"kbs": ["hr", "made_up_kb"]}),  # unknown KB ignore hona chahiye
        json.dumps({"questions": ["sick leave?"]}),
        json.dumps({"relevant": [0, 0, 99]}),  # duplicate + out of range
        "Sick leave is 30 days. [leave_policy.md]",
        json.dumps({"grounded": False, "unsupported": ["30 days"]}),
        "Sick leave is 12 days per year. [leave_policy.md]",
        json.dumps({"grounded": True}),
    ]
    llm = ScriptedLLM(script)
    r = CorrectiveRAG(llm, kbs).run("sick leave?")
    assert r.route == ["hr"] and len(r.passages) == 1
    assert r.grounded is True and "12 days" in r.answer
    assert "unsupported claims" in llm.calls[5][-1].content  # feedback regeneration prompt mein gaya


def test_tool_calling_agent_decides_to_search(kbs):
    llm = ScriptedLLM(offline_agentic_llm)
    res = build_rag_agent(llm, kbs, NullTracer()).run("What is the hotel cap per night for employees?")
    assert "6000" in res.output and "[travel_expenses.md]" in res.output
    tool_msgs = [m for m in res.messages if m.role == "tool"]
    assert tool_msgs and tool_msgs[0].name == "search_hr"


def test_agent_can_search_multiple_times(kbs):
    script = [
        tool_response(call("search_product", query="refund window")),
        tool_response(call("search_hr", query="sick leave")),
        "30 days [refund_policy.md]; 12 sick days [leave_policy.md]",
    ]
    res = build_rag_agent(ScriptedLLM(script), kbs, NullTracer()).run("refund window and sick leave?")
    assert [m.name for m in res.messages if m.role == "tool"] == ["search_product", "search_hr"]
