"""Lamba page -> chunks -> sawaal se sabse relevant chunks.

Ek Wikipedia page 50k+ characters ka ho sakta hai. Poora LLM ko bhejna mehenga hai aur model
beech ki info 'miss' kar deta hai (lost-in-the-middle). Isliye mini-RAG:
  split into chunks (paragraph boundaries pe, thoda overlap) -> score vs question -> top-k bhejo
"""
from __future__ import annotations

import re

from agentkit import Embedder, cosine, get_embedder

_WORD = re.compile(r"[a-z0-9]+")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for para in paras:
        while len(para) > max_chars:  # bahut lamba paragraph: hard split
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap:]
        if len(cur) + len(para) + 1 > max_chars and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n" + para if overlap else para  # overlap: context na toote
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


def top_chunks(chunks: list[str], question: str, k: int = 3, embedder: Embedder | None = None) -> list[str]:
    """Embedding similarity + exact keyword overlap. Original order mein return (padhne mein natural)."""
    if len(chunks) <= k:
        return chunks
    emb = embedder or get_embedder("local")
    qv = emb.embed_one(question)
    q_words = set(_WORD.findall(question.lower()))
    vecs = emb.embed(chunks)
    scored = []
    for i, (c, v) in enumerate(zip(chunks, vecs)):
        overlap = len(q_words & set(_WORD.findall(c.lower()))) / (len(q_words) or 1)
        scored.append((cosine(qv, v) + 0.5 * overlap, i))
    best = sorted(i for _, i in sorted(scored, reverse=True)[:k])
    return [chunks[i] for i in best]
