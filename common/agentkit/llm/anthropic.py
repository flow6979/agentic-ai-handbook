"""Anthropic (Claude) native adapter.

OpenAI se differences (yahi 'adapter' ka kaam hai):
- system prompt alag `system` field mein jata hai, messages mein nahi
- tool calls `content` blocks (`tool_use`) ke roop mein aate hain
- tool results `user` role ke andar `tool_result` block mein bhejte hain
"""
from __future__ import annotations

from typing import Any

from . import http
from .base import LLM
from .types import LLMError, LLMResponse, Message, ToolCall, Usage

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicLLM(LLM):
    provider = "anthropic"

    def __init__(self, model: str, api_key: str | None, timeout: float = 60.0):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _to_wire(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system = "\n\n".join(m.content or "" for m in messages if m.role == "system")
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or ""}
                # Consecutive tool results ek hi user message mein jaane chahiye
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = [{"type": "text", "text": m.content}] if m.content else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content or ""})
        return system, out

    def chat(self, messages, tools=None, *, temperature=0.0, max_tokens=1024, json_mode=False) -> LLMResponse:
        system, wire = self._to_wire(messages)
        if json_mode:  # Anthropic mein json_mode flag nahi hai, instruction se karwate hain
            system += "\n\nRespond with a single valid JSON object only. No prose, no code fences."
        body: dict[str, Any] = {"model": self.model, "messages": wire, "max_tokens": max_tokens, "temperature": temperature}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        headers = {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01", "content-type": "application/json"}
        if http.IN_BROWSER:  # browser se seedha call ke liye Anthropic yeh opt-in header maangta hai
            headers["anthropic-dangerous-direct-browser-access"] = "true"
        try:
            r = http.post_json(API_URL, body, headers=headers, timeout=self.timeout)
        except http.TransportError as e:
            raise LLMError(f"anthropic network error: {e}", retryable=True) from e
        if r.status >= 400:
            raise LLMError(
                f"anthropic HTTP {r.status}: {r.text[:300]}",
                status=r.status,
                retryable=r.status in (429, 529) or r.status >= 500,
            )
        data = r.json()
        text = "".join(b["text"] for b in data["content"] if b["type"] == "text") or None
        calls = [ToolCall(b["id"], b["name"], b["input"]) for b in data["content"] if b["type"] == "tool_use"]
        u = data.get("usage") or {}
        return LLMResponse(
            content=text,
            tool_calls=calls,
            usage=Usage(u.get("input_tokens", 0), u.get("output_tokens", 0)),
            model=data.get("model", self.model),
            stop_reason=data.get("stop_reason", ""),
            raw=data,
        )
