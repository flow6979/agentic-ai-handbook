"""OpenAI-compatible adapter.

Bahut saare providers OpenAI ka `/chat/completions` format follow karte hain:
OpenAI, Groq, OpenRouter, Together, DeepSeek, Ollama (local), aur Gemini ka
OpenAI-compatible endpoint. Isliye ek hi adapter se sab cover ho jaate hain,
sirf `base_url` aur `api_key` badalta hai.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .base import LLM
from .types import LLMError, LLMResponse, Message, ToolCall, ToolSpec, Usage


class OpenAICompatLLM(LLM):
    def __init__(self, model: str, base_url: str, api_key: str | None, provider: str = "openai", timeout: float = 60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider = provider
        self.timeout = timeout

    # --- translation: neutral -> OpenAI format -------------------------------
    @staticmethod
    def _to_wire(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""}
        out: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            out["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in m.tool_calls
            ]
        return out

    def chat(self, messages, tools=None, *, temperature=0.0, max_tokens=1024, json_mode=False) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [self._to_wire(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        except httpx.TransportError as e:  # network glitch, timeout
            raise LLMError(f"{self.provider} network error: {e}", retryable=True) from e
        if r.status_code >= 400:
            # 429 (rate limit) aur 5xx (server issue) retry karne layak hain; 400/401 nahi.
            raise LLMError(
                f"{self.provider} HTTP {r.status_code}: {r.text[:300]}",
                status=r.status_code,
                retryable=r.status_code == 429 or r.status_code >= 500,
            )
        return self._from_wire(r.json())

    # --- translation: OpenAI format -> neutral -------------------------------
    def _from_wire(self, data: dict[str, Any]) -> LLMResponse:
        choice = data["choices"][0]
        msg = choice["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            raw_args = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"_raw": raw_args}  # model ne tooti JSON di; agent loop isko error ki tarah handle karega
            calls.append(ToolCall(id=c["id"], name=c["function"]["name"], arguments=args))
        u = data.get("usage") or {}
        return LLMResponse(
            content=msg.get("content"),
            tool_calls=calls,
            usage=Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
            model=data.get("model", self.model),
            stop_reason=choice.get("finish_reason", ""),
            raw=data,
        )
