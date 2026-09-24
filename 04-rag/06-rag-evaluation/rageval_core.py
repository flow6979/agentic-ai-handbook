"""RAG evaluation: retrieval metrics (hit rate, MRR, recall) + LLM-as-judge generation metrics.

"Mujhe lagta hai better hai" ko numbers mein badalna. Har change (chunk size, embedder, k, prompt)
ke baad yeh eval chalao, compare karo, phir decide karo.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from agentkit import LLM, Embedder, Message, cosine, llm_json


# ------------------------------------------------------------ dataset
@dataclass
class EvalItem:
    question: str
    relevant_sources: list[str]
    reference_answer: str = ""


def load_eval_set(path: str | Path) -> list[EvalItem]:
    return [EvalItem(**d) for d in json.loads(Path(path).read_text())]


def load_docs(folder: str | Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(Path(folder).glob("*.md"))}


# ------------------------------------------------------------ configurable index (what we are evaluating)
def chunk_fixed(text: str, size: int, overlap: int = 0) -> list[str]:
    step = max(size - overlap, 1)
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]


def chunk_paragraphs(text: str, size: int, overlap: int = 0) -> list[str]:
    out, buf = [], ""
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if buf and len(buf) + len(para) > size:
            out.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    return out + ([buf] if buf else [])


CHUNKERS = {"fixed": chunk_fixed, "paragraph": chunk_paragraphs}


@dataclass
class RetrievalConfig:
    name: str
    chunker: str = "paragraph"
    size: int = 400
    overlap: int = 0
    k: int = 3


class Index:
    def __init__(self, docs: dict[str, str], cfg: RetrievalConfig, embedder: Embedder):
        self.cfg, self.embedder = cfg, embedder
        self.chunks = [(src, c) for src, text in docs.items() for c in CHUNKERS[cfg.chunker](text, cfg.size, cfg.overlap)]
        self.vecs = embedder.embed([c for _, c in self.chunks])

    def retrieve(self, query: str, k: int | None = None) -> list[tuple[str, str]]:
        q = self.embedder.embed_one(query)
        order = sorted(range(len(self.chunks)), key=lambda i: cosine(q, self.vecs[i]), reverse=True)
        return [self.chunks[i] for i in order[: k or self.cfg.k]]


# ------------------------------------------------------------ retrieval metrics
def hit_at_k(retrieved: list[str], relevant: list[str]) -> float:
    """Top-k mein kam se kam ek relevant source aaya? 1 ya 0."""
    return 1.0 if set(retrieved) & set(relevant) else 0.0


def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    """Pehla relevant result kis rank pe? rank 1 -> 1.0, rank 2 -> 0.5, rank 3 -> 0.33, nahi mila -> 0."""
    for i, src in enumerate(retrieved, 1):
        if src in relevant:
            return 1.0 / i
    return 0.0


def recall_at_k(retrieved: list[str], relevant: list[str]) -> float:
    """Jitne relevant sources chahiye the, unme se kitne top-k mein aaye (multi-doc questions ke liye)."""
    return len(set(retrieved) & set(relevant)) / len(set(relevant)) if relevant else 0.0


@dataclass
class RetrievalReport:
    config: str
    hit_rate: float
    mrr: float
    recall: float
    num_chunks: int
    failures: list[str] = field(default_factory=list)  # jin questions pe hit nahi hua: yahi debug karo


def evaluate_retrieval(retrieve: Callable[[str], list[tuple[str, str]]], dataset: list[EvalItem],
                       config_name: str = "", num_chunks: int = 0) -> RetrievalReport:
    hits, rrs, recalls, fails = [], [], [], []
    for item in dataset:
        sources = [src for src, _ in retrieve(item.question)]
        # same doc ke kai chunks aa sakte hain: rank ke liye unique order rakho
        sources = list(dict.fromkeys(sources))
        h = hit_at_k(sources, item.relevant_sources)
        hits.append(h)
        rrs.append(reciprocal_rank(sources, item.relevant_sources))
        recalls.append(recall_at_k(sources, item.relevant_sources))
        if not h:
            fails.append(item.question)
    n = len(dataset) or 1
    return RetrievalReport(config_name, sum(hits) / n, sum(rrs) / n, sum(recalls) / n, num_chunks, fails)


def compare_configs(docs: dict[str, str], dataset: list[EvalItem], configs: list[RetrievalConfig],
                    embedder: Embedder) -> list[RetrievalReport]:
    reports = []
    for cfg in configs:
        idx = Index(docs, cfg, embedder)
        reports.append(evaluate_retrieval(idx.retrieve, dataset, cfg.name, len(idx.chunks)))
    return reports


# ------------------------------------------------------------ generation metrics: LLM-as-judge
class Judgement(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str = ""


FAITHFULNESS_PROMPT = """TASK:FAITHFULNESS
You are a strict evaluator. Score 1-5 how well the ANSWER is supported by the CONTEXT.
5 = every claim is supported. 1 = mostly unsupported or contradicts the context.
Judge only support by the context, not general truth.
CONTEXT:
{context}
ANSWER: {answer}"""

RELEVANCE_PROMPT = """TASK:RELEVANCE
Score 1-5 how directly the ANSWER addresses the QUESTION. 5 = fully answers it, 1 = off-topic.
QUESTION: {question}
ANSWER: {answer}"""

CORRECTNESS_PROMPT = """TASK:CORRECTNESS
Score 1-5 how well the ANSWER matches the REFERENCE answer in meaning (not wording).
QUESTION: {question}
REFERENCE: {reference}
ANSWER: {answer}"""


def judge(llm: LLM, prompt: str) -> Judgement:
    return llm_json(llm, prompt, Judgement)


@dataclass
class GenerationReport:
    faithfulness: float
    relevance: float
    correctness: float
    rows: list[dict] = field(default_factory=list)


ANSWER_SYSTEM = "Answer ONLY from the context, concisely. If the context lacks the answer, say you don't know."


def generate_answer(llm: LLM, question: str, context: list[tuple[str, str]]) -> str:
    ctx = "\n\n".join(f"[{s}] {t}" for s, t in context)
    return llm.chat([Message.system(ANSWER_SYSTEM), Message.user(f"CONTEXT:\n{ctx}\n\nQUESTION: {question}")]).content or ""


def evaluate_generation(answer_llm: LLM, judge_llm: LLM, index: Index, dataset: list[EvalItem]) -> GenerationReport:
    rows = []
    for item in dataset:
        ctx = index.retrieve(item.question)
        answer = generate_answer(answer_llm, item.question, ctx)
        context_text = "\n".join(t for _, t in ctx)
        f = judge(judge_llm, FAITHFULNESS_PROMPT.format(context=context_text, answer=answer))
        r = judge(judge_llm, RELEVANCE_PROMPT.format(question=item.question, answer=answer))
        c = judge(judge_llm, CORRECTNESS_PROMPT.format(question=item.question, reference=item.reference_answer, answer=answer))
        rows.append({"question": item.question, "answer": answer, "faithfulness": f.score, "relevance": r.score,
                     "correctness": c.score, "why_low": min((f, r, c), key=lambda j: j.score).reason})
    n = len(rows) or 1
    avg = lambda key: sum(row[key] for row in rows) / n  # noqa: E731
    return GenerationReport(avg("faithfulness"), avg("relevance"), avg("correctness"), rows)


# ------------------------------------------------------------ offline fakes
def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 2}


def offline_answerer(messages, tools):
    """Nakli answer LLM: context ka sabse zyada overlap wala sentence."""
    last = messages[-1].content or ""
    q = _words(last.rsplit("QUESTION:", 1)[-1])
    sents = re.split(r"(?<=[.!?])\s+|\n", last.split("QUESTION:")[0])
    best = max(sents, key=lambda s: len(q & _words(s)), default="")
    return re.sub(r"^\[[^\]]+\]\s*", "", best.strip()) or "I don't know."


def offline_judge(messages, tools):
    """Nakli judge: word overlap ko 1-5 score mein map karta hai. Asli judge meaning samajhta hai."""
    last = (messages[-1].content or "").split("\n\nReturn ONLY a JSON object")[0]
    kind = re.match(r"TASK:(\w+)", last).group(1)
    answer = _words(last.rsplit("ANSWER:", 1)[-1])
    if kind == "FAITHFULNESS":
        base = _words(last.split("CONTEXT:", 1)[1].rsplit("ANSWER:", 1)[0])
    elif kind == "RELEVANCE":
        base = _words(last.split("QUESTION:", 1)[1].split("ANSWER:")[0])
    else:
        base = _words(last.split("REFERENCE:", 1)[1].split("ANSWER:")[0])
    ratio = len(answer & base) / max(len(answer if kind == "FAITHFULNESS" else base), 1)
    score = 1 + round(4 * min(ratio, 1.0))
    return json.dumps({"score": score, "reason": f"word overlap {ratio:.2f}"})
