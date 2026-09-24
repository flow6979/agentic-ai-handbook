"""Embeddings: text -> numbers ka vector, taaki 'meaning' se search kar sakein.

get_embedder("local")                          # offline, free, no deps (hashing trick). Demo/test ke liye.
get_embedder("openai:text-embedding-3-small")
get_embedder("gemini:text-embedding-004")
get_embedder("ollama:nomic-embed-text")        # local real model

'local' embedder asli semantic model nahi hai: yeh words ke hash se vector banata hai,
isliye synonyms nahi samajhta ('car' != 'automobile'). Lekin same words wale texts ko
paas rakhta hai, jo RAG pipeline samajhne ke liye kaafi hai. Real use mein model wala lo.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

import httpx

from .llm.factory import OPENAI_COMPAT, _load_dotenv


class Embedder(ABC):
    dim: int = 0

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder(Embedder):
    """Words (+ word pairs) ko hash karke fixed-size vector mein daalo, phir normalize."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        words = _WORD.findall(text.lower())
        grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed(self, texts):
        return [self._vec(t) for t in texts]


class OpenAICompatEmbedder(Embedder):
    def __init__(self, model: str, base_url: str, api_key: str | None):
        self.model, self.base_url, self.api_key = model, base_url.rstrip("/"), api_key

    def embed(self, texts):
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = httpx.post(f"{self.base_url}/embeddings", json={"model": self.model, "input": texts}, headers=headers, timeout=60)
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


def get_embedder(spec: str | None = None) -> Embedder:
    _load_dotenv()
    spec = spec or os.getenv("EMBED_MODEL") or "local"
    if spec == "local":
        return HashingEmbedder()
    provider, model = spec.split(":", 1)
    base_url, key_env = OPENAI_COMPAT[provider]
    return OpenAICompatEmbedder(model, base_url, os.getenv(key_env) if key_env else None)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
