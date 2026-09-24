import pytest

from agentkit import NullTracer, ScriptedLLM, call, tool_response
from react_native import run_react_native
from react_textloop import parse_step, run_react_text, truncate_hallucinated_observation
from react_tools import TOOLS, calculator, lookup, safe_eval

TOOL_MAP = {t.name: t for t in TOOLS}


def test_safe_eval_blocks_code():
    assert safe_eval("(2 + 3) * 4") == 20
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('ls')")


def test_lookup_fuzzy():
    assert "8849" in lookup.run({"query": "how tall is everest"})
    assert "No entry" in lookup.run({"query": "zzz"})


def test_parse_action_and_final():
    kind, name, args, thought = parse_step('Thought: x\nAction: calculator\nAction Input: {"expression": "1+1"}', TOOL_MAP)
    assert (kind, name, args, thought) == ("action", "calculator", {"expression": "1+1"}, "x")
    assert parse_step("Thought: done\nFinal Answer: 42", TOOL_MAP)[:2] == ("final", "42")


def test_parse_plain_string_input_for_single_arg_tool():
    kind, name, args, _ = parse_step("Thought: t\nAction: lookup\nAction Input: eiffel tower height", TOOL_MAP)
    assert kind == "action" and args == {"query": "eiffel tower height"}


def test_parse_unknown_tool_is_invalid():
    assert parse_step('Action: google\nAction Input: {"q": "x"}', TOOL_MAP)[0] == "invalid"


def test_truncate_fake_observation():
    assert truncate_hallucinated_observation("Action: a\nAction Input: {}\nObservation: fake") == "Action: a\nAction Input: {}"


def test_text_loop_end_to_end_with_format_error_recovery():
    llm = ScriptedLLM([
        "I think the answer is big.",  # format galat -> FORMAT ERROR observation
        'Thought: look up\nAction: lookup\nAction Input: {"query": "mount everest height"}\nObservation: 1 m',
        'Thought: calc\nAction: calculator\nAction Input: {"expression": "8849 / 330"}',
        "Thought: I now know the final answer\nFinal Answer: about 26.8",
    ])
    r = run_react_text(llm, TOOLS, "q", tracer=NullTracer())
    assert r.answer == "about 26.8"
    assert r.llm_calls == 4
    assert r.steps[0].observation.startswith("FORMAT ERROR")
    assert "8849" in r.steps[1].observation  # real tool result, not the hallucinated "1 m"
    # Model ko jo observation bheja gaya woh real tha:
    assert any(m.content.startswith("Observation: Mount Everest is 8849") for m in llm.calls[-1] if m.role == "user")


def test_text_loop_max_steps():
    llm = ScriptedLLM(lambda m, t: 'Thought: again\nAction: calculator\nAction Input: {"expression": "1"}')
    r = run_react_text(llm, TOOLS, "q", max_steps=3, tracer=NullTracer())
    assert r.stopped_reason == "max_steps" and r.llm_calls == 3


def test_native_style():
    llm = ScriptedLLM([tool_response(call("calculator", expression="2**10")), "1024"])
    r = run_react_native(llm, "2^10?", tracer=NullTracer())
    assert r.output == "1024"
    assert [m.content for m in r.messages if m.role == "tool"] == ["1024"]
    assert llm.calls[0] and calculator.name == "calculator"
