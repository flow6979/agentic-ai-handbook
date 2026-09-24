"""RAG from scratch: load -> chunk -> embed -> store -> retrieve -> augment prompt -> generate.

Koi framework nahi (LangChain / LlamaIndex nahi), taaki har step dikhe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agentkit import LLM, Embedder, Message, cosine


# ---------------------------------------------------------------- 1. LOAD
@dataclass
class Document:
    id: str  # usually file name; citations mein yahi dikhta hai
    text: str
    metadata: dict = field(default_factory=dict)


def load_folder(folder: str | Path, exts: tuple[str, ...] = (".md", ".txt")) -> list[Document]:
    docs = []
    for p in sorted(Path(folder).iterdir()):
        if p.suffix.lower() in exts:
            docs.append(Document(id=p.name, text=p.read_text(encoding="utf-8"), metadata={"path": str(p)}))
    return docs


# ---------------------------------------------------------------- 2. CHUNK
def chunk_fixed(text: str, size: int = 400, overlap: int = 80) -> list[str]:
    """Har `size` characters pe kaato, `overlap` chars peeche se dobara lo.

    Simple aur predictable, lekin words/sentences beech se toot jaate hain.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    step = size - overlap
    return [text[i : i + size].strip() for i in range(0, max(len(text) - overlap, 1), step) if text[i : i + size].strip()]


def chunk_recursive(text: str, size: int = 400, separators: tuple[str, ...] = ("\n\n", "\n", ". ", " ")) -> list[str]:
    """Pehle bade 'natural' boundary (paragraph) pe todo; koi piece bada ho to chhote separator se.

    LangChain ka RecursiveCharacterTextSplitter yahi karta hai. Structure maintain rehta hai.
    """
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    if not separators:  # koi separator nahi bacha: hard cut
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, rest = separators[0], separators[1:]
    pieces = [p for p in text.split(sep) if p.strip()]
    chunks, buf = [], ""
    for piece in pieces:
        candidate = f"{buf}{sep}{piece}" if buf else piece
        if len(candidate) <= size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf.strip())
        if len(piece) > size:  # akela piece hi bada hai: agle separator se todo
            chunks.extend(chunk_recursive(piece, size, rest))
            buf = ""
        else:
            buf = piece
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


_SENT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def chunk_sentences(text: str, max_chars: int = 400) -> list[str]:
    """Poore sentences ko jodte jao jab tak max_chars na ho jaaye. Kabhi sentence nahi tootta."""
    sents = [s.strip() for s in _SENT.split(text) if s.strip()]
    chunks, buf = [], ""
    for s in sents:
        if buf and len(buf) + 1 + len(s) > max_chars:
            chunks.append(buf)
            buf = s
        else:
            buf = f"{buf} {s}".strip()
    if buf:
        chunks.append(buf)
    return chunks


CHUNKERS = {"fixed": chunk_fixed, "recursive": chunk_recursive, "sentence": chunk_sentences}


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


def chunk_documents(docs: list[Document], strategy: str = "recursive", size: int = 400) -> list[Chunk]:
    fn = CHUNKERS[strategy]
    out = []
    for d in docs:
        pieces = fn(d.text, size) if strategy != "sentence" else fn(d.text, max_chars=size)
        for i, piece in enumerate(pieces):
            out.append(Chunk(id=f"{d.id}#{i}", text=piece, source=d.id, metadata={**d.metadata, "chunk": i}))
    return out


# ---------------------------------------------------------------- 3+4. EMBED + STORE
class InMemoryVectorStore:
    """Sabse simple vector DB: list mein (chunk, vector) rakho, har query pe sab se cosine nikaalo.

    O(N) per query. 10k chunks tak theek; uske baad ANN index (HNSW) wala real DB chahiye.
    """

    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.items: list[tuple[Chunk, list[float]]] = []

    def add(self, chunks: list[Chunk], batch_size: int = 64) -> None:
        for i in range(0, len(chunks), batch_size):  # batching: API calls kam
            batch = chunks[i : i + batch_size]
            vectors = self.embedder.embed([c.text for c in batch])
            self.items.extend(zip(batch, vectors))

    # ------------------------------------------------------------ 5. RETRIEVE
    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        q = self.embedder.embed_one(query)
        scored = [(c, cosine(q, v)) for c, v in self.items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


# ---------------------------------------------------------------- 6+7. AUGMENT + GENERATE
SYSTEM_PROMPT = """You answer questions using ONLY the numbered context passages.
Rules:
- Cite every fact with its source in square brackets, e.g. [refund_policy.md].
- If the context does not contain the answer, reply exactly: I don't know based on the provided documents.
- Do not use outside knowledge. Be concise."""

IDK = "I don't know based on the provided documents."


def build_prompt(question: str, hits: list[tuple[Chunk, float]]) -> str:
    blocks = [f"[{i}] (source: {c.source})\n{c.text}" for i, (c, _) in enumerate(hits, 1)]
    return "CONTEXT:\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}"


@dataclass
class RAGAnswer:
    text: str
    sources: list[str]
    hits: list[tuple[Chunk, float]]
    prompt: str = ""


class RAG:
    def __init__(self, llm: LLM, store: InMemoryVectorStore, k: int = 4, min_score: float = 0.12):
        self.llm, self.store, self.k, self.min_score = llm, store, k, min_score

    def answer(self, question: str) -> RAGAnswer:
        hits = [h for h in self.store.search(question, self.k) if h[1] >= self.min_score]
        if not hits:
            # Retrieval gate: kuch relevant mila hi nahi to LLM ko guess karne ka mauka hi mat do
            return RAGAnswer(IDK, [], [])
        prompt = build_prompt(question, hits)
        text = self.llm.chat([Message.system(SYSTEM_PROMPT), Message.user(prompt)]).content or ""
        cited = sorted({s for s in re.findall(r"\[([^\]\s]+\.(?:md|txt|pdf))\]", text)})
        return RAGAnswer(text, cited, hits, prompt)


def build_rag(folder: str | Path, llm: LLM, embedder: Embedder, strategy: str = "recursive", size: int = 400, k: int = 4) -> RAG:
    store = InMemoryVectorStore(embedder)
    store.add(chunk_documents(load_folder(folder), strategy, size))
    return RAG(llm, store, k=k)


def offline_answerer(messages, tools):
    """ScriptedLLM function: 'nakli LLM'. Context ka woh sentence uthata hai jisme question ke
    sabse zyada words hain, aur uska source cite karta hai. Sirf demo/test ke liye; asli LLM
    samajh ke jawab likhta hai, yeh sirf copy karta hai."""
    prompt = messages[-1].content or ""
    question = prompt.rsplit("QUESTION:", 1)[-1].lower()
    qwords = {w for w in re.findall(r"[a-z0-9]+", question) if len(w) > 3}
    best, best_score = None, 0
    for source, body in re.findall(r"\[\d+\] \(source: ([^)]+)\)\n(.+?)(?=\n\n\[\d+\] \(source|\n\nQUESTION:)", prompt, re.S):
        text = " ".join(l for l in body.splitlines() if l.strip() and not l.startswith("#"))
        for sent in re.split(r"(?<=[.!?])\s+", text):
            score = len(qwords & set(re.findall(r"[a-z0-9]+", sent.lower())))
            if score > best_score:
                best, best_score = (sent, source), score
    if not best:
        return IDK
    return f"{best[0]} [{best[1]}]"
