import json

from agentkit import NullTracer, ScriptedLLM
from reflection_reflexion import LessonMemory, extract_code, solve_with_reflexion
from reflection_refine import self_refine
from reflection_sandbox import run_tests

j = json.dumps
TESTS = ["assert add(2, 3) == 5", "assert add(-1, 1) == 0"]


def test_sandbox_pass_fail_timeout_syntax():
    assert run_tests("def add(a, b):\n    return a + b", TESTS).passed
    bad = run_tests("def add(a, b):\n    return abs(a) + b", TESTS)
    assert not bad.passed and bad.n_failed == 1 and "FAIL: assert add(-1, 1) == 0" in bad.output
    assert "TIMEOUT" in run_tests("while True:\n    pass", TESTS, timeout=1).output
    assert run_tests("def add(a, b) return", TESTS).n_failed == 2  # syntax error


def test_extract_code():
    assert extract_code("here:\n```python\nx = 1\n```\nbye") == "x = 1"
    assert extract_code("x = 2") == "x = 2"


def test_self_refine_revises_until_approved():
    llm = ScriptedLLM([
        "draft v1",
        j({"score": 3, "approved": False, "issues": ["missing price"]}),
        "draft v2 with price",
        j({"score": 9, "approved": True, "issues": []}),
    ])
    res = self_refine(llm, "task", tracer=NullTracer())
    assert res.final == "draft v2 with price" and res.approved and len(res.rounds) == 2
    # Reviewer ki issues revise prompt mein gayi:
    assert "missing price" in llm.calls[2][-1].content


def test_self_refine_stops_at_max_rounds():
    llm = ScriptedLLM(lambda m, t: j({"score": 2, "approved": False, "issues": ["bad"]})
                      if "Draft:" in (m[-1].content or "") else "some draft")
    res = self_refine(llm, "t", max_rounds=2, tracer=NullTracer())
    assert not res.approved and len(res.rounds) == 2


def test_reflexion_learns_and_persists(tmp_path):
    llm = ScriptedLLM([
        "```python\ndef add(a, b):\n    return a - b\n```",
        "I subtracted instead of adding. Lesson: read the operation carefully.",
        "```python\ndef add(a, b):\n    return a + b\n```",
    ])
    mem_file = tmp_path / "lessons.json"
    res = solve_with_reflexion(llm, "write add", TESTS, memory=LessonMemory(mem_file), tracer=NullTracer())
    assert res.solved and len(res.attempts) == 2
    # Lesson agle attempt ke prompt mein tha:
    assert "read the operation carefully" in llm.calls[2][-1].content
    # Aur file mein persist hua (naya run bhi yaad rakhega):
    assert LessonMemory(mem_file).lessons == ["I subtracted instead of adding. Lesson: read the operation carefully."]
