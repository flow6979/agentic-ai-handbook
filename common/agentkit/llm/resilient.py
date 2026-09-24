"""Production resilience: retry with backoff + fallback across providers.

Real duniya mein LLM APIs fail hoti hain: rate limit (429), overload (529/503),
network timeout. Production agent ko inse bachna padta hai:

  RetryingLLM   -> same provider pe exponential backoff ke saath dobara try
  FallbackLLM   -> pehla provider fail? agla try karo (e.g. OpenAI -> Groq -> Ollama)
"""
from __future__ import annotations

import logging
import random
import time

from .base import LLM
from .types import LLMError, LLMResponse

log = logging.getLogger("agentkit.llm")


class RetryingLLM(LLM):
    def __init__(self, inner: LLM, max_retries: int = 3, base_delay: float = 1.0, sleep=time.sleep):
        self.inner = inner
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._sleep = sleep  # tests mein sleep ko fake kar sakte hain
        self.provider, self.model = inner.provider, inner.model

    def chat(self, messages, tools=None, **kw) -> LLMResponse:
        for attempt in range(self.max_retries + 1):
            try:
                return self.inner.chat(messages, tools, **kw)
            except LLMError as e:
                if not e.retryable or attempt == self.max_retries:
                    raise
                # Exponential backoff + jitter: 1s, 2s, 4s... (+random) taaki sab clients ek saath retry na karein
                delay = self.base_delay * (2**attempt) + random.uniform(0, 0.25)
                log.warning("LLM %s failed (%s), retry %d in %.1fs", self.inner, e, attempt + 1, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")


class FallbackLLM(LLM):
    provider = "fallback"

    def __init__(self, llms: list[LLM]):
        if not llms:
            raise ValueError("FallbackLLM needs at least one LLM")
        self.llms = llms
        self.model = "|".join(repr(l) for l in llms)

    def chat(self, messages, tools=None, **kw) -> LLMResponse:
        errors = []
        for llm in self.llms:
            try:
                return llm.chat(messages, tools, **kw)
            except LLMError as e:
                log.warning("LLM %s failed, falling back: %s", llm, e)
                errors.append(f"{llm}: {e}")
        raise LLMError("All LLMs failed:\n" + "\n".join(errors))
