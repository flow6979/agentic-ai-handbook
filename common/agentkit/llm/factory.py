"""get_llm("provider:model"): ek string se koi bhi LLM banao.

Examples:
    get_llm("openai:gpt-4o-mini")
    get_llm("anthropic:claude-sonnet-5")
    get_llm("gemini:gemini-3.8-flash")
    get_llm("groq:llama-3.3-70b-versatile")
    get_llm("ollama:llama3.1")                 # local, free, no key
    get_llm("openrouter:meta-llama/llama-3.3-70b-instruct")
    get_llm()                                  # env var LLM_MODEL se
    get_llm("groq:llama-3.3-70b-versatile,ollama:llama3.1")   # comma = fallback chain

Code mein kabhi model hardcode mat karo; config (env) se lo. Model badalna = config change,
code change nahi. Yeh production ka basic rule hai.
"""
from __future__ import annotations

import os

from .anthropic import AnthropicLLM
from .base import LLM
from .openai_compat import OpenAICompatLLM
from .resilient import FallbackLLM, RetryingLLM

# provider -> (base_url, api key env var). Sab OpenAI-compatible hain.
OPENAI_COMPAT = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "ollama": (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), None),
}

DEFAULT_MODEL = "ollama:llama3.1"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _single(spec: str, api_key: str | None = None) -> LLM:
    if ":" not in spec:
        raise ValueError(f"LLM spec must be 'provider:model', got {spec!r}")
    provider, model = spec.split(":", 1)
    provider = provider.strip().lower()
    if provider == "anthropic":
        return AnthropicLLM(model, api_key or os.getenv("ANTHROPIC_API_KEY"))
    if provider in OPENAI_COMPAT:
        base_url, key_env = OPENAI_COMPAT[provider]
        key = api_key or (os.getenv(key_env) if key_env else None)
        if key_env and not key:
            raise ValueError(f"{provider} needs {key_env} in env / .env")
        return OpenAICompatLLM(model, base_url, key, provider=provider)
    raise ValueError(f"Unknown provider {provider!r}. Known: anthropic, {', '.join(OPENAI_COMPAT)}")


def get_llm(spec: str | None = None, *, retries: int = 3, api_keys: dict[str, str] | None = None) -> LLM:
    """`api_keys` = {"groq": "...", "gemini": "..."}: env ki jagah yeh keys use hongi.

    Browser UI (agent-lab) isi se har request pe user ki key deta hai; key kahin save nahi hoti.
    """
    _load_dotenv()
    spec = spec or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    keys = {k.lower(): v for k, v in (api_keys or {}).items() if v}
    parts = [s.strip() for s in spec.split(",") if s.strip()]
    chain = [RetryingLLM(_single(p, keys.get(p.split(":", 1)[0].lower())), max_retries=retries) for p in parts]
    return chain[0] if len(chain) == 1 else FallbackLLM(chain)
