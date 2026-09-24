"""Chat with a PDF.

    python 04-rag/02-pdf-chat/main.py ask data/nimbuskart_handbook.pdf "How many paid leave days do I get?"
    python 04-rag/02-pdf-chat/main.py chat data/nimbuskart_handbook.pdf
    python 04-rag/02-pdf-chat/main.py chat --offline          # default sample PDF, no key
"""
import argparse
from pathlib import Path

from agentkit import ScriptedLLM, get_embedder, get_llm
from pdfchat_core import PDFChat, PDFIndex, offline_pdf_llm

SAMPLE = Path(__file__).parent / "data" / "nimbuskart_handbook.pdf"


def build(pdf: str, offline: bool) -> PDFChat:
    index = PDFIndex(get_embedder())
    report = index.add_pdf(pdf)
    print(f"[loaded {pdf}: {len(report.pages)} pages, {len(index.items)} chunks"
          + (f", pages with no text: {report.empty_pages}" if report.empty_pages else "") + "]")
    return PDFChat(ScriptedLLM(offline_pdf_llm) if offline else get_llm(), index)


def show(turn, verbose: bool) -> None:
    if turn.standalone != turn.question:
        print(f"  (standalone query: {turn.standalone})")
    if verbose:
        for c, s in turn.hits:
            print(f"  {s:.3f} p.{c.page} {c.text[:70]!r}")
    print(turn.answer)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["ask", "chat"])
    ap.add_argument("pdf", nargs="?", default=str(SAMPLE))
    ap.add_argument("question", nargs="?", default="How many paid leave days do I get?")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="retrieved chunks dikhao")
    args = ap.parse_args()

    chat = build(args.pdf, args.offline)
    if args.mode == "ask":
        show(chat.ask(args.question), args.verbose)
        return
    print("Ask about the PDF. Empty line to quit. Try a follow-up like 'and sick leave?'")
    while True:
        try:
            q = input("you> ").strip()
        except EOFError:
            break
        if not q:
            break
        show(chat.ask(q), args.verbose)


if __name__ == "__main__":
    main()
