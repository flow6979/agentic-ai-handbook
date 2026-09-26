"""RAG lab: 04-rag/02-pdf-chat ko UI se chalao (PDF -> chunks -> embeddings -> retrieve -> answer).

params:
    action: "ingest" | "ask"
    source: "sample" (bundled nimbuskart_handbook.pdf) | "upload" (pdf_b64 = base64 PDF bytes) | "text" (text = pasted text)
    chunk_size, overlap, strategy: "lines" (project ka page-aware chunker) | "fixed" | "recursive" | "sentence"
    question, top_k, min_score
    no_rag: bool      -> retrieval ke bina seedha LLM se poochho (hallucination contrast)
    history: [{"q": "...", "a": "..."}]  -> follow-up ko standalone query mein badalna (condense_question)

UI events (type="step"):
    stage   {stage: load|chunk|embed|store|retrieve|generate, status: start|done, detail, ms}
    chunks  {chunks: [{id, page, score, text}]}
    answer  {text, pages}
Browser (Pyodide) mein Python state runs ke beech bani rehti hai, isliye index `_CACHE` mein rakhte hain.
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import time
from typing import Any

from agentkit import Message, ScriptedLLM, cosine

from .registry import Lab
from .runtime import ROOT, LabContext, meter, use_project

PROJECT = "04-rag/02-pdf-chat"
SAMPLE_PDF = ROOT / PROJECT / "data" / "nimbuskart_handbook.pdf"
MAX_UPLOAD = 5 * 1024 * 1024  # 5 MB: browser memory aur embedding cost dono ke liye
DEFAULT_Q = "How many days of sick leave do employees get, and when is a doctor's note needed?"
STRATEGIES = ("lines", "fixed", "recursive", "sentence")

# key -> {"chunks": [PDFChunk], "vecs": [...], "pages": int, "source": str, "embedder": str}
_CACHE: dict[str, dict[str, Any]] = {}

# Retrieval ke bina "confident" lekin galat jawab: LLM ne document dekha hi nahi.
NO_RAG_OFFLINE = ("Most companies give around 7 to 10 sick days a year, and a doctor's note is usually needed "
                  "after 3 days. (No document was used, so this is a generic guess.)")


def _embedder_label(emb) -> str:
    model = getattr(emb, "model", None)
    return f"{model} (API embeddings)" if model else "local hashing embedder (offline, word-based)"


def _load_pages(ctx: LabContext):
    """Source se pages lao. Returns (pages, source_name, raw_bytes_for_hash)."""
    use_project(PROJECT)
    from pdfchat_core import Page, _clean
    from pypdf import PdfReader

    source = ctx.params.get("source", "sample")
    if source == "text":
        text = str(ctx.params.get("text") or "").strip()
        if len(text) < 20:
            raise ValueError("Pasted text is too short (need at least 20 characters).")
        # Blank-line blocks ko "pages" maano taaki citations kaam karein
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()] or [text]
        return [Page(i, _clean(b)) for i, b in enumerate(blocks, 1)], "pasted-text", text.encode()
    if source == "upload":
        raw = base64.b64decode(str(ctx.params.get("pdf_b64") or ""), validate=False)
        if not raw:
            raise ValueError("No PDF uploaded.")
        if len(raw) > MAX_UPLOAD:
            raise ValueError(f"PDF is {len(raw) // 1024} KB; the browser lab limit is {MAX_UPLOAD // 1024} KB.")
        name = str(ctx.params.get("filename") or "upload.pdf")
    else:
        raw = SAMPLE_PDF.read_bytes()
        name = SAMPLE_PDF.name
    reader = PdfReader(io.BytesIO(raw))
    pages = [Page(i, _clean(p.extract_text() or "")) for i, p in enumerate(reader.pages, 1)]
    if pages and all(len(p.text) < 20 for p in pages):
        raise ValueError("No extractable text on any page. This looks like a scanned PDF; it needs OCR first "
                         "(Tesseract / ocrmypdf / a vision LLM). See 04-rag/02-pdf-chat/CONCEPTS.md.")
    return pages, name, raw


def _chunk(pages, source: str, strategy: str, size: int, overlap: int):
    use_project(PROJECT)
    use_project("04-rag/01-rag-basics")
    from pdfchat_core import PDFChunk, chunk_pages

    if strategy == "lines":
        return chunk_pages(pages, source, size=size, overlap=overlap)
    import ragbasics_pipeline as rb

    out = []
    for pg in pages:
        if strategy == "fixed":
            parts = rb.chunk_fixed(pg.text, size=size, overlap=overlap)
        elif strategy == "sentence":
            parts = rb.chunk_sentences(pg.text, max_chars=size)
        else:
            parts = rb.chunk_recursive(pg.text, size=size)
        out += [PDFChunk(f"{source}:p{pg.number}#{i}", t, pg.number, source) for i, t in enumerate(parts) if t.strip()]
    return out


def _stage(ctx: LabContext, stage: str, status: str, detail: str = "", ms: float | None = None) -> None:
    ctx.step("stage", detail or stage, stage=stage, status=status, ms=None if ms is None else round(ms))


def _ingest(ctx: LabContext) -> tuple[str, dict[str, Any]]:
    p = ctx.params
    strategy = p.get("strategy", "lines")
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    size, overlap = int(p.get("chunk_size", 500)), int(p.get("overlap", 100))
    emb = ctx.embedder()
    label = _embedder_label(emb)

    t = time.perf_counter()
    _stage(ctx, "load", "start")
    pages, source, raw = _load_pages(ctx)
    _stage(ctx, "load", "done", f"{len(pages)} pages from {source}", (time.perf_counter() - t) * 1000)

    key = hashlib.sha256(raw + f"|{strategy}|{size}|{overlap}|{label}".encode()).hexdigest()[:16]
    if key in _CACHE:
        for s in ("chunk", "embed", "store"):
            _stage(ctx, s, "done", "cached (same document + settings)", 0)
        return key, _CACHE[key]

    t = time.perf_counter()
    _stage(ctx, "chunk", "start")
    chunks = _chunk(pages, source, strategy, size, overlap)
    if not chunks:
        raise ValueError("Chunking produced no chunks.")
    _stage(ctx, "chunk", "done", f"{len(chunks)} chunks ({strategy}, size {size}, overlap {overlap})", (time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    _stage(ctx, "embed", "start", label)
    vecs = emb.embed([c.text for c in chunks])
    _stage(ctx, "embed", "done", f"{len(vecs)} vectors x {len(vecs[0])} dims · {label}", (time.perf_counter() - t) * 1000)

    _stage(ctx, "store", "start")
    entry = {"chunks": chunks, "vecs": vecs, "pages": len(pages), "source": source, "embedder": label, "emb": emb}
    _CACHE[key] = entry
    _stage(ctx, "store", "done", f"in-memory vector store: {len(chunks)} items", 0)
    return key, entry


def _offline_llm():
    use_project(PROJECT)
    from pdfchat_core import offline_pdf_llm

    def fn(messages, tools):
        last = messages[-1].content or ""
        if last.startswith("NO_RAG:"):
            return NO_RAG_OFFLINE
        return offline_pdf_llm(messages, tools)

    return ScriptedLLM(fn, model="scripted")


def _ask(ctx: LabContext) -> dict[str, Any]:
    use_project(PROJECT)
    from pdfchat_core import ANSWER_SYSTEM, condense_question

    p = ctx.params
    question = str(p.get("question") or DEFAULT_Q).strip()
    llm = meter(_offline_llm(), ctx.emit) if ctx.offline else ctx.llm()

    if p.get("no_rag"):
        _stage(ctx, "generate", "start", "no retrieval: the LLM answers from memory")
        t = time.perf_counter()
        prompt = question if not ctx.offline else f"NO_RAG: {question}"
        answer = llm.chat([Message.user(prompt)]).content or ""
        _stage(ctx, "generate", "done", "answered without the document", (time.perf_counter() - t) * 1000)
        ctx.step("answer", answer, pages=[], grounded=False)
        return {"answer": answer, "pages": [], "no_rag": True, "question": question, "chunks": [], **llm.stats()}

    key, entry = _ingest(ctx)
    history = [(h.get("q", ""), h.get("a", "")) for h in (p.get("history") or []) if isinstance(h, dict)]
    standalone = condense_question(llm, history, question) if history else question

    t = time.perf_counter()
    _stage(ctx, "retrieve", "start", standalone)
    k, min_score = int(p.get("top_k", 3)), float(p.get("min_score", 0.1))
    qv = entry["emb"].embed_one(standalone)
    scored = sorted(((c, cosine(qv, v)) for c, v in zip(entry["chunks"], entry["vecs"])), key=lambda x: x[1], reverse=True)[:k]
    chunks_out = [{"id": c.id, "page": c.page, "score": round(s, 3), "text": c.text} for c, s in scored]
    ctx.step("chunks", f"top {len(scored)} chunks", chunks=chunks_out, min_score=min_score)
    _stage(ctx, "retrieve", "done", f"top {len(scored)} of {len(entry['chunks'])} (best score {scored[0][1]:.2f})", (time.perf_counter() - t) * 1000)

    good = [(c, s) for c, s in scored if s >= min_score]
    t = time.perf_counter()
    _stage(ctx, "generate", "start")
    if not good:
        # Gate: context bahut kamzor hai to LLM ko bulao hi mat, seedha "nahi mila" bolo (hallucination se bachao)
        answer = "I couldn't find that in the document."
        _stage(ctx, "generate", "done", f"skipped: best score below min_score {min_score}", 0)
    else:
        context = "\n\n".join(f"[p.{c.page}] {c.text}" for c, _ in good)
        msgs = [Message.system(ANSWER_SYSTEM)]
        for q, a in history[-4:]:
            msgs += [Message.user(q), Message.assistant(a)]
        msgs.append(Message.user(f"EXCERPTS:\n{context}\n\nQUESTION: {standalone}"))
        answer = llm.chat(msgs).content or ""
        _stage(ctx, "generate", "done", f"answer from {len(good)} excerpts", (time.perf_counter() - t) * 1000)
    pages = sorted({int(x) for x in re.findall(r"\[p\.(\d+)\]", answer)})
    ctx.step("answer", answer, pages=pages, grounded=bool(good))
    return {"answer": answer, "pages": pages, "question": question, "standalone": standalone, "chunks": chunks_out,
            "embedder": entry["embedder"], "n_chunks": len(entry["chunks"]), "no_rag": False, "gated": not good,
            "steps": len(chunks_out), **llm.stats()}


def run(ctx: LabContext) -> dict[str, Any]:
    if ctx.params.get("action", "ask") == "ingest":
        _, entry = _ingest(ctx)
        return {"ingested": True, "source": entry["source"], "pages": entry["pages"], "n_chunks": len(entry["chunks"]),
                "embedder": entry["embedder"], "answer": ""}
    return _ask(ctx)


LAB = Lab(
    id="rag",
    project=PROJECT,
    run=run,
    pip=["pypdf"],
    defaults={"action": "ask", "source": "sample", "chunk_size": 500, "overlap": 100, "strategy": "lines",
              "question": DEFAULT_Q, "top_k": 3, "min_score": 0.1},
    smoke_cases=[{"action": "ingest"}, {"action": "ask"}, {"action": "ask", "no_rag": True},
                 {"action": "ask", "strategy": "recursive", "chunk_size": 300}],
)
