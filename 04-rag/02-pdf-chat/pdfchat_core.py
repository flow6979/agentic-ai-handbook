"""Chat with a PDF: page-aware ingestion, page citations, follow-up question condensation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from agentkit import LLM, Embedder, Message, cosine


# ------------------------------------------------------------ ingestion
@dataclass
class Page:
    number: int  # 1-based, jaisa user PDF viewer mein dekhta hai
    text: str


@dataclass
class PDFLoadReport:
    pages: list[Page]
    empty_pages: list[int] = field(default_factory=list)  # text nahi mila: shayad scanned image -> OCR chahiye

    @property
    def looks_scanned(self) -> bool:
        return bool(self.pages) and len(self.empty_pages) == len(self.pages)


def _clean(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # line-end hyphenation jodo: "reim-\nbursed" -> "reimbursed"
    text = re.sub(r"^\s*Page \d+\s*$", "", text, flags=re.M)  # header/footer noise hatao
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def load_pdf(path: str | Path) -> PDFLoadReport:
    reader = PdfReader(str(path))
    pages, empty = [], []
    for i, p in enumerate(reader.pages, 1):
        text = _clean(p.extract_text() or "")
        if len(text) < 20:
            empty.append(i)
        pages.append(Page(i, text))
    return PDFLoadReport(pages, empty)


@dataclass
class PDFChunk:
    id: str
    text: str
    page: int
    source: str


def chunk_pages(pages: list[Page], source: str, size: int = 500, overlap: int = 100) -> list[PDFChunk]:
    """Page ke andar hi chunk karo taaki har chunk ka ek clear page number ho (citation ke liye).

    Trade-off: agar paragraph do pages mein bata hai to woh do chunks mein tootega.
    """
    out = []
    for pg in pages:
        lines = [l for l in pg.text.splitlines() if l.strip()]
        buf: list[str] = []
        idx = 0
        for line in lines:
            if buf and sum(len(b) + 1 for b in buf) + len(line) > size:
                out.append(PDFChunk(f"{source}:p{pg.number}#{idx}", "\n".join(buf), pg.number, source))
                idx += 1
                # overlap: last kuch lines agle chunk mein bhi rakho
                keep, total = [], 0
                for b in reversed(buf):
                    if total + len(b) > overlap:
                        break
                    keep.insert(0, b)
                    total += len(b)
                buf = keep
            buf.append(line)
        if buf:
            out.append(PDFChunk(f"{source}:p{pg.number}#{idx}", "\n".join(buf), pg.number, source))
    return out


class PDFIndex:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.items: list[tuple[PDFChunk, list[float]]] = []

    def add_pdf(self, path: str | Path) -> PDFLoadReport:
        report = load_pdf(path)
        if report.looks_scanned:
            raise ValueError(
                f"{path}: no extractable text on any page. It is probably a scanned PDF; run OCR "
                "(e.g. Tesseract / ocrmypdf / a vision LLM) first."
            )
        chunks = chunk_pages(report.pages, Path(path).name)
        vecs = self.embedder.embed([c.text for c in chunks])
        self.items.extend(zip(chunks, vecs))
        return report

    def search(self, query: str, k: int = 4) -> list[tuple[PDFChunk, float]]:
        q = self.embedder.embed_one(query)
        return sorted(((c, cosine(q, v)) for c, v in self.items), key=lambda x: x[1], reverse=True)[:k]


# ------------------------------------------------------------ chat
CONDENSE_PROMPT = """TASK:CONDENSE
Rewrite the follow-up question into a standalone question that can be understood without the chat history.
Keep it short. Return only the rewritten question.

CHAT HISTORY:
{history}

FOLLOW-UP QUESTION: {question}"""

ANSWER_SYSTEM = """You answer questions about a PDF using ONLY the given excerpts.
Cite the page for every fact like [p.3]. If the excerpts do not contain the answer, say:
I couldn't find that in the document."""


def condense_question(llm: LLM, history: list[tuple[str, str]], question: str, max_turns: int = 4) -> str:
    """Follow-up ("aur sick leave?") ko standalone query ("How many sick leave days per year?") banao.

    Kyun? Retrieval sirf current query dekhta hai. "aur uska?" embed karoge to kuch relevant nahi milega.
    """
    if not history:
        return question
    hist = "\n".join(f"User: {q}\nAssistant: {a}" for q, a in history[-max_turns:])
    out = llm.chat([Message.user(CONDENSE_PROMPT.format(history=hist, question=question))]).content or ""
    return out.strip() or question


@dataclass
class ChatTurn:
    question: str
    standalone: str
    answer: str
    pages: list[int]
    hits: list[tuple[PDFChunk, float]]


class PDFChat:
    def __init__(self, llm: LLM, index: PDFIndex, k: int = 4):
        self.llm, self.index, self.k = llm, index, k
        self.history: list[tuple[str, str]] = []

    def ask(self, question: str) -> ChatTurn:
        standalone = condense_question(self.llm, self.history, question)
        hits = self.index.search(standalone, self.k)
        context = "\n\n".join(f"[p.{c.page}] {c.text}" for c, _ in hits)
        msgs = [Message.system(ANSWER_SYSTEM)]
        # History bhi bhejte hain taaki answer ka tone/continuity bane; lekin facts sirf excerpts se
        for q, a in self.history[-4:]:
            msgs += [Message.user(q), Message.assistant(a)]
        msgs.append(Message.user(f"EXCERPTS:\n{context}\n\nQUESTION: {standalone}"))
        answer = self.llm.chat(msgs).content or ""
        pages = sorted({int(p) for p in re.findall(r"\[p\.(\d+)\]", answer)})
        self.history.append((question, answer))
        return ChatTurn(question, standalone, answer, pages, hits)


# ------------------------------------------------------------ offline fake LLM
def offline_pdf_llm(messages, tools):
    """Nakli LLM (demo/test only).
    - CONDENSE: "and sick leave?" / "what about X" jaise prefixes hata ke standalone-ish query banata hai.
      (Asli LLM history padh ke "How many sick leave days per year?" jaisa likhega.)
    - ANSWER: excerpts ka woh sentence jisme question ke sabse zyada words hain, + page cite."""
    last = messages[-1].content or ""
    if last.startswith("TASK:CONDENSE"):
        follow = last.rsplit("FOLLOW-UP QUESTION:", 1)[-1].strip()
        return re.sub(r"^(and|aur|what about|how about)\s+", "", follow, flags=re.I)
    question = last.rsplit("QUESTION:", 1)[-1].lower()
    qwords = {w for w in re.findall(r"[a-z0-9]+", question) if len(w) > 3}
    best, score = None, 0
    for page, body in re.findall(r"\[p\.(\d+)\] (.+?)(?=\n\n\[p\.|\n\nQUESTION:)", last, re.S):
        for sent in re.split(r"(?<=[.;])\s+|\n(?=[A-Z])", body.replace("\n", " \n")):
            sent = " ".join(sent.split())
            s = len(qwords & set(re.findall(r"[a-z0-9]+", sent.lower())))
            if s > score:
                best, score = (sent, page), s
    return f"{best[0]} [p.{best[1]}]" if best else "I couldn't find that in the document."
