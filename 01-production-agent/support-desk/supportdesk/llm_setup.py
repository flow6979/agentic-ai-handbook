"""LLM banana: config -> get_llm() -> (retry + fallback chain). Provider ka naam kahin hardcode nahi.

    LLM_MODEL=groq:llama-3.3-70b-versatile,gemini:gemini-3.8-flash,ollama:llama3.1
             └─ primary ─────────────────┘ └─ backup 1 ─────────┘ └─ backup 2 ─┘
Har link RetryingLLM hai (429/5xx pe backoff), poori chain FallbackLLM.
"""
from __future__ import annotations

from agentkit import LLM, get_llm

from .config import Settings


class ConfigError(RuntimeError):
    pass


def build_llm(settings: Settings) -> LLM:
    try:
        return get_llm(settings.llm_model)
    except ValueError as e:
        raise ConfigError(
            f"LLM config problem: {e}\n"
            "Fix: repo root pe .env banao (cp .env.example .env), LLM_MODEL + us provider ki API key bharo.\n"
            "Ya bina key ke flow dekhne ke liye --offline flag use karo."
        ) from e
