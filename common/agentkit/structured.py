"""Structured output: LLM se free text nahi, validated JSON (Pydantic model) lo.

Kyun? Agent ke output ko code consume karta hai (router ka decision, planner ka plan,
grader ka score). Text parse karna fragile hai. Pattern:
  1. schema prompt mein do + json_mode on karo
  2. response se JSON nikaalo (code fences hata ke)
  3. Pydantic se validate karo
  4. fail? error model ko wapas bhejo aur retry karo
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .llm import LLM, Message

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> dict | list:
    """'```json {...} ```' ya prose ke beech se pehla JSON object/array nikaalo."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON found in: {text[:200]!r}")


def llm_json(llm: LLM, prompt: str, schema: type[T], *, system: str | None = None, retries: int = 2) -> T:
    schema_str = json.dumps(schema.model_json_schema())
    messages = []
    if system:
        messages.append(Message.system(system))
    messages.append(Message.user(f"{prompt}\n\nReturn ONLY a JSON object matching this JSON Schema:\n{schema_str}"))
    last_err = None
    for _ in range(retries + 1):
        resp = llm.chat(messages, json_mode=True)
        try:
            return schema.model_validate(extract_json(resp.content or ""))
        except (ValueError, ValidationError) as e:
            last_err = e
            # Self-correction: model ko uski galti dikhao
            messages += [Message.assistant(resp.content), Message.user(f"That was invalid: {e}. Return corrected JSON only.")]
    raise ValueError(f"LLM failed to produce valid {schema.__name__}: {last_err}")
