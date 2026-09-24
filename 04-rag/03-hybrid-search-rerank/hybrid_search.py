"""Hybrid retrieval: BM25 (keyword) + vector (meaning) -> Reciprocal Rank Fusion -> LLM rerank.

    query ──┬──► BM25 ranking ────┐
            │                     ├──► RRF fuse ──► top-N candidates ──► LLM listwise rerank ──► top-k
            └──► vector ranking ──┘
    (dono se pehle metadata filter: category="troubleshooting", year>=2025 ...)
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from agentkit import LLM, Embedder, cosine, llm_json


@dataclass
class Doc:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def load_docs(path: str | Path) -> list[Doc]:
    return [Doc(**d) for d in json.loads(Path(path).read_text())]


# ------------------------------------------------------------ tokenization
STOPWORDS = set("a an the is are was were of to in on for and or with my your how what does do i it this that my".split())
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")  # "nk-4471", "e-1042" ek token rahe


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def light_stem(token: str) -> str:
    """Bahut basic stemmer: "refunds"->"refund", "charging"->"charg". Real mein Porter/Snowball stemmer
    ya lemmatizer use hota hai. Iske bina BM25 "refund" query pe "Refunds" wala doc miss kar deta hai."""
    if "-" in token or token.isdigit():
        return token
    for suf in ("ing", "ed", "es", "s"):
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return token[: -len(suf)]
    return token


# ------------------------------------------------------------ BM25 from scratch
class BM25:
    """Okapi BM25: classic keyword search (Elasticsearch/Lucene ka default scorer).

    score(q, d) = sum over query terms t of:
        IDF(t) * tf(t,d) * (k1 + 1) / (tf(t,d) + k1 * (1 - b + b * |d| / avgdl))

    - IDF: rare word = zyada important ("nk-4471" rare hai, "earbuds" common)
    - tf saturation (k1): ek word 10 baar aane se 10x score nahi milta
    - length normalisation (b): lambe docs ko sirf lambe hone ka fayda nahi
    """

    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75, stem: bool = True):
        self.docs, self.k1, self.b, self.stem = docs, k1, b, stem
        self.tfs = [Counter(self._terms(d.text)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = sum(self.lens) / max(len(docs), 1)
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(docs)
        self.idf = {t: math.log((n - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def _terms(self, text: str) -> list[str]:
        toks = tokenize(text)
        return [light_stem(t) for t in toks] if self.stem else toks

    def scores(self, query: str) -> list[float]:
        q = self._terms(query)
        out = []
        for tf, dl in zip(self.tfs, self.lens):
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


class VectorIndex:
    def __init__(self, docs: list[Doc], embedder: Embedder):
        self.docs = docs
        self.embedder = embedder
        self.vecs = embedder.embed([d.text for d in docs])

    def scores(self, query: str) -> list[float]:
        q = self.embedder.embed_one(query)
        return [cosine(q, v) for v in self.vecs]


# ------------------------------------------------------------ fusion
def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """RRF: score(d) = sum 1/(k + rank). Sirf rank use hota hai, raw score nahi.

    Kyun? BM25 scores 0..15 hote hain, cosine 0..1. Inhe seedha jodna apples + oranges hai.
    Rank sabki same scale pe hai. k=60 paper ka default hai: top ranks ka fark smooth karta hai.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, 1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


# ------------------------------------------------------------ metadata filter
Filter = dict[str, Any] | Callable[[dict[str, Any]], bool]


def matches(meta: dict[str, Any], flt: Filter | None) -> bool:
    """{"category": "policy"} = equality; {"year": (">=", 2025)} = comparison; ya koi function."""
    if flt is None:
        return True
    if callable(flt):
        return flt(meta)
    for key, cond in flt.items():
        val = meta.get(key)
        if isinstance(cond, tuple):
            op, target = cond
            if op == ">=":
                ok = val is not None and val >= target
            elif op == "<=":
                ok = val is not None and val <= target
            elif op == "in":
                ok = val in target
            elif op == "!=":
                ok = val != target
            else:
                raise ValueError(f"unknown filter op {op!r}")
            if not ok:
                return False
        elif val != cond:
            return False
    return True


# ------------------------------------------------------------ retriever
@dataclass
class SearchResult:
    doc: Doc
    score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None


class HybridRetriever:
    def __init__(self, docs: list[Doc], embedder: Embedder):
        self.docs = docs
        self.bm25 = BM25(docs)
        self.vec = VectorIndex(docs, embedder)
        self.by_id = {d.id: d for d in docs}

    def _rank(self, scores: list[float], allowed: set[int], drop_zero: bool) -> list[str]:
        idx = [i for i in allowed if not (drop_zero and scores[i] <= 0)]
        idx.sort(key=lambda i: scores[i], reverse=True)
        return [self.docs[i].id for i in idx]

    def search(self, query: str, k: int = 5, mode: str = "hybrid", flt: Filter | None = None,
               candidates: int = 20) -> list[SearchResult]:
        allowed = {i for i, d in enumerate(self.docs) if matches(d.metadata, flt)}  # pre-filter
        bm = self._rank(self.bm25.scores(query), allowed, drop_zero=True)[:candidates]
        vr = self._rank(self.vec.scores(query), allowed, drop_zero=False)[:candidates]
        bm_pos = {d: i + 1 for i, d in enumerate(bm)}
        vr_pos = {d: i + 1 for i, d in enumerate(vr)}
        if mode == "bm25":
            ranked = [(d, 1.0 / r) for d, r in bm_pos.items()]
        elif mode == "vector":
            ranked = [(d, 1.0 / r) for d, r in vr_pos.items()]
        else:
            ranked = reciprocal_rank_fusion([bm, vr])
        return [SearchResult(self.by_id[d], s, bm_pos.get(d), vr_pos.get(d)) for d, s in ranked[:k]]


# ------------------------------------------------------------ LLM rerank (listwise)
class Rerank(BaseModel):
    ranking: list[int]  # candidate numbers, most relevant first


RERANK_PROMPT = """TASK:RERANK
Rank the candidate passages by how well they answer the query. Most relevant first.
Leave out passages that are irrelevant.

QUERY: {query}

CANDIDATES:
{candidates}"""


def llm_rerank(llm: LLM, query: str, results: list[SearchResult], top_n: int = 3) -> list[SearchResult]:
    """Listwise rerank: saare candidates ek prompt mein, LLM order batata hai.

    Retrieval (BM25/vector) fast lekin 'shallow' hai. Reranker query aur passage ko SAATH padhta hai,
    isliye zyada accurate hai, lekin slow/mehenga, isliye sirf top ~20 candidates pe chalate hain.
    """
    if not results:
        return []
    cands = "\n".join(f"[{i}] {r.doc.text}" for i, r in enumerate(results))
    out = llm_json(llm, RERANK_PROMPT.format(query=query, candidates=cands), Rerank)
    seen, ordered = set(), []
    for i in out.ranking:  # LLM galat/duplicate index de sakta hai: validate karo
        if 0 <= i < len(results) and i not in seen:
            seen.add(i)
            ordered.append(results[i])
    return ordered[:top_n]


def offline_reranker(messages, tools):
    """Nakli reranker: candidates ko query ke saath token-overlap se sort karta hai."""
    prompt = messages[-1].content or ""
    query = re.search(r"QUERY: (.+)", prompt).group(1)
    q = set(tokenize(query))
    cands = re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M)
    scored = sorted(((len(q & set(tokenize(t))), int(i)) for i, t in cands), key=lambda x: (-x[0], x[1]))
    return json.dumps({"ranking": [i for s, i in scored if s > 0]})
