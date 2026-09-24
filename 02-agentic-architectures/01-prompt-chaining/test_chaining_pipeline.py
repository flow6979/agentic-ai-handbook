import json

import pytest
from chaining_pipeline import GateError, Outline, check_draft, check_outline, offline_demo_llm, write_blog

from agentkit import ScriptedLLM


def test_outline_gate_rules():
    check_outline(Outline(title="t", sections=["a", "b", "c"]))
    with pytest.raises(GateError):
        check_outline(Outline(title="t", sections=["a", "b"]))
    with pytest.raises(GateError):
        check_outline(Outline(title="t", sections=["a", "A ", "b"]))


def test_draft_gate_catches_missing_section():
    o = Outline(title="t", sections=["Alpha", "Beta", "Gamma"])
    with pytest.raises(GateError, match="Gamma"):
        check_draft("## Alpha\n" + "word " * 50 + "\n## Beta", o)


def test_full_chain_retries_failed_gate_with_feedback():
    llm = offline_demo_llm()
    res = write_blog(llm, "Python async")
    assert res.outline.sections[0] == "Why async"
    assert res.log[0].startswith("outline: gate failed") and res.log[1] == "outline: ok (attempt 2)"
    # retry prompt mein gate ka feedback gaya
    assert "duplicate section headings" in llm.calls[1][-1].content
    assert "Most network calls" in res.final
    assert len(llm.calls) == 4  # outline x2, draft, polish


def test_chain_stops_when_gate_keeps_failing():
    bad = json.dumps({"title": "x", "sections": ["only one"]})
    llm = ScriptedLLM([bad, bad])
    with pytest.raises(GateError, match="outline failed after 2 attempts"):
        write_blog(llm, "anything")
