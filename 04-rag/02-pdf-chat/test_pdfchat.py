from pathlib import Path

import pytest

from agentkit import ScriptedLLM, get_embedder
from pdfchat_core import (Page, PDFChat, PDFIndex, _clean, chunk_pages, condense_question, load_pdf,
                          offline_pdf_llm)

PDF = Path(__file__).parent / "data" / "nimbuskart_handbook.pdf"


def test_load_pdf_pages_and_cleanup():
    rep = load_pdf(PDF)
    assert len(rep.pages) == 4 and rep.empty_pages == []
    assert "24 days of paid leave" in rep.pages[1].text
    assert "Page 2" not in rep.pages[1].text  # footer hata diya
    assert _clean("reim-\nbursed") == "reimbursed"


def test_chunks_keep_page_numbers():
    chunks = chunk_pages(load_pdf(PDF).pages, "h.pdf", size=200, overlap=60)
    assert {c.page for c in chunks} == {1, 2, 3, 4}
    assert all(c.id.startswith(f"h.pdf:p{c.page}#") for c in chunks)


def test_scanned_pdf_detected(tmp_path, monkeypatch):
    import pdfchat_core
    from pdfchat_core import PDFLoadReport

    monkeypatch.setattr(pdfchat_core, "load_pdf", lambda p: PDFLoadReport([Page(1, ""), Page(2, "")], [1, 2]))
    with pytest.raises(ValueError, match="OCR"):
        PDFIndex(get_embedder("local")).add_pdf("scan.pdf")


def test_condense_skipped_without_history():
    llm = ScriptedLLM([])
    assert condense_question(llm, [], "How many leave days?") == "How many leave days?"
    assert llm.calls == []


def test_answer_cites_page_and_followup_is_condensed():
    idx = PDFIndex(get_embedder("local"))
    idx.add_pdf(PDF)
    chat = PDFChat(ScriptedLLM(offline_pdf_llm), idx)

    t1 = chat.ask("How many days of paid leave per year?")
    assert t1.pages == [2] and "24 days" in t1.answer

    t2 = chat.ask("and what is the hotel cap per night?")
    assert t2.standalone != t2.question  # condense step chala
    assert t2.pages == [3] and "6000" in t2.answer
    assert len(chat.history) == 2
