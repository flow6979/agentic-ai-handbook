from typing import Literal

import pytest
from pydantic import BaseModel

from agentkit import (Agent, FallbackLLM, LLMError, Message, NullTracer, RetryingLLM, ScriptedLLM, call, cosine,
                      extract_json, get_embedder, llm_json, tool, tool_response)
from agentkit.llm.anthropic import AnthropicLLM
from agentkit.llm.openai_compat import OpenAICompatLLM


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def boom(x: str) -> str:
    """Always fails."""
    raise RuntimeError("kaboom")


def test_tool_schema_from_type_hints():
    @tool
    def weather(city: str, unit: Literal["c", "f"] = "c", days: list[int] | None = None) -> str:
        """Get weather."""
        return ""

    p = weather.parameters
    assert p["required"] == ["city"]
    assert p["properties"]["unit"] == {"type": "string", "enum": ["c", "f"]}
    assert p["properties"]["days"] == {"type": "array", "items": {"type": "integer"}}


def test_agent_runs_tool_then_answers():
    llm = ScriptedLLM([tool_response(call("add", a=2, b=3)), "The answer is 5."])
    res = Agent(llm, [add], tracer=NullTracer()).run("2+3?")
    assert res.output == "The answer is 5."
    assert res.steps == 2
    tool_msg = [m for m in res.messages if m.role == "tool"][0]
    assert tool_msg.content == "5"


def test_tool_error_is_sent_back_not_raised():
    llm = ScriptedLLM([tool_response(call("boom", x="1")), tool_response(call("nope")), "gave up"])
    res = Agent(llm, [boom], tracer=NullTracer()).run("go")
    errors = [m.content for m in res.messages if m.role == "tool"]
    assert "kaboom" in errors[0] and "unknown tool" in errors[1]


def test_max_steps_guard():
    llm = ScriptedLLM(lambda msgs, tools: tool_response(call("add", a=1, b=1)))
    res = Agent(llm, [add], max_steps=3, tracer=NullTracer()).run("loop forever")
    assert res.stopped_reason == "max_steps" and res.steps == 3


def test_human_approval_can_reject():
    llm = ScriptedLLM([tool_response(call("add", a=1, b=1)), "ok"])
    res = Agent(llm, [add], approve=lambda n, a: False, tracer=NullTracer()).run("x")
    assert "rejected" in [m for m in res.messages if m.role == "tool"][0].content


class Flaky(ScriptedLLM):
    def __init__(self, fails, status=429):
        super().__init__(["ok"])
        self.fails, self.status = fails, status

    def chat(self, *a, **k):
        if self.fails:
            self.fails -= 1
            raise LLMError("fail", status=self.status, retryable=self.status == 429)
        return super().chat(*a, **k)


def test_retry_then_success():
    llm = RetryingLLM(Flaky(2), max_retries=3, sleep=lambda s: None)
    assert llm.chat([Message.user("hi")]).content == "ok"


def test_non_retryable_raises_immediately():
    inner = Flaky(1, status=401)
    with pytest.raises(LLMError):
        RetryingLLM(inner, sleep=lambda s: None).chat([Message.user("hi")])


def test_fallback_uses_next_provider():
    llm = FallbackLLM([Flaky(5, status=401), ScriptedLLM(["from backup"])])
    assert llm.chat([Message.user("hi")]).content == "from backup"


def test_extract_json_and_llm_json_self_corrects():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}

    class Out(BaseModel):
        score: int

    llm = ScriptedLLM(['{"score": "high"}', '{"score": 7}'])
    assert llm_json(llm, "rate it", Out).score == 7


def test_local_embedder_similarity():
    e = get_embedder("local")
    a, b, c = e.embed(["refund policy for orders", "how do refunds for orders work", "python async tutorial"])
    assert cosine(a, b) > cosine(a, c)


def test_openai_wire_roundtrip():
    tc = call("add", a=1, b=2)
    wire = OpenAICompatLLM._to_wire(Message.assistant(None, [tc]))
    assert wire["tool_calls"][0]["function"]["name"] == "add"
    llm = OpenAICompatLLM("m", "http://x", None)
    resp = llm._from_wire({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "1", "function": {"name": "add", "arguments": '{"a":1,"b":2}'}}]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    assert resp.tool_calls[0].arguments == {"a": 1, "b": 2} and resp.usage.output_tokens == 4


def test_anthropic_wire_groups_tool_results():
    c1, c2 = call("add", a=1, b=1), call("add", a=2, b=2)
    system, wire = AnthropicLLM._to_wire([
        Message.system("sys"), Message.user("hi"), Message.assistant(None, [c1, c2]),
        Message.tool(c1, "2"), Message.tool(c2, "4"),
    ])
    assert system == "sys"
    assert wire[1]["content"][0]["type"] == "tool_use"
    assert [b["tool_use_id"] for b in wire[2]["content"]] == [c1.id, c2.id]
