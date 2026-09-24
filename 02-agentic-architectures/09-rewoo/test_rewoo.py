import pytest

from agentkit import NullTracer, ScriptedLLM
from rewoo_agent import ReWOO, dependency_levels, parse_plan
from rewoo_tools import TOOLS

NAMES = {"lookup", "calculator", "LLM"}
PLAN = ("Plan: a\n#E1 = lookup[mount everest height in metres]\n"
        "Plan: b\n#E2 = lookup[eiffel tower height in metres]\n"
        "Plan: c\n#E3 = calculator[#E1 / #E2]")


def test_parse_plan_and_levels():
    steps = parse_plan(PLAN, NAMES)
    assert [(s.var, s.tool) for s in steps] == [("#E1", "lookup"), ("#E2", "lookup"), ("#E3", "calculator")]
    assert steps[2].deps == {"#E1", "#E2"} and steps[0].reason == "a"
    assert [[s.var for s in lvl] for lvl in dependency_levels(steps)] == [["#E1", "#E2"], ["#E3"]]


def test_parse_rejects_bad_plans():
    with pytest.raises(ValueError, match="unknown tool"):
        parse_plan("#E1 = google[x]", NAMES)
    with pytest.raises(ValueError, match="before they are defined"):
        parse_plan("#E1 = calculator[#E2 + 1]\n#E2 = lookup[x]", NAMES)
    with pytest.raises(ValueError, match="no '#E"):
        parse_plan("I think the answer is 5", NAMES)


def test_end_to_end_only_two_llm_calls():
    llm = ScriptedLLM([PLAN, "about 26.8 times"])
    r = ReWOO(llm, TOOLS, tracer=NullTracer()).run("ratio?")
    assert r.answer == "about 26.8 times"
    assert r.llm_calls == 2  # planner + solver, tools ke beech koi LLM nahi
    assert [s.evidence for s in r.steps] == ["8849", "330", "26.8152"]
    solver_prompt = llm.calls[1][-1].content
    assert "Evidence: 26.8152" in solver_prompt


def test_worker_error_becomes_evidence_and_llm_worker():
    llm = ScriptedLLM([
        "Plan: x\n#E1 = lookup[zzz qqq]\nPlan: y\n#E2 = LLM[Summarise: #E1]",
        "summary of error",  # LLM worker
        "final",
    ])
    r = ReWOO(llm, TOOLS, tracer=NullTracer(), parallel=False).run("t")
    assert r.steps[0].evidence.startswith("ERROR: LookupError")
    assert "Summarise: ERROR" in llm.calls[1][-1].content  # #E1 substitute hua
    assert r.llm_calls == 3 and r.answer == "final"
