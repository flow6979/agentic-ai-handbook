from pathlib import Path

import pytest

from agentkit import ScriptedLLM, get_embedder
from ragbasics_pipeline import (IDK, InMemoryVectorStore, build_rag, chunk_documents, chunk_fixed, chunk_recursive,
                                chunk_sentences, load_folder, offline_answerer)

DATA = Path(__file__).parent / "data"
TEXT = ("Para one sentence. Another one here.\n\n" * 10) + "x" * 900


def test_fixed_chunks_overlap():
    chunks = chunk_fixed("abcdefghij" * 10, size=30, overlap=10)
    assert all(len(c) <= 30 for c in chunks)
    assert chunks[0][-10:] == chunks[1][:10]  # overlap: pichhle ke last 10 == agle ke first 10
    with pytest.raises(ValueError):
        chunk_fixed("abc", size=10, overlap=10)


def test_recursive_respects_size_and_hard_cuts_long_words():
    chunks = chunk_recursive(TEXT, size=200)
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0].startswith("Para one")  # paragraph boundary pe kata


def test_sentence_chunker_never_splits_sentence():
    chunks = chunk_sentences("A b c. D e f. G h i.", max_chars=8)
    assert chunks == ["A b c.", "D e f.", "G h i."]


def test_chunk_ids_and_sources():
    chunks = chunk_documents(load_folder(DATA), "recursive", 400)
    assert {c.source for c in chunks} >= {"refund_policy.md", "shipping.md"}
    assert chunks[0].id.endswith("#0")


def test_retrieval_finds_right_doc():
    store = InMemoryVectorStore(get_embedder("local"))
    store.add(chunk_documents(load_folder(DATA)))
    top = store.search("How long do card refunds take?", k=1)[0][0]
    assert top.source == "refund_policy.md"


def test_answer_has_citation_and_context_in_prompt():
    llm = ScriptedLLM(offline_answerer)
    ans = build_rag(DATA, llm, get_embedder("local")).answer("Is express shipping free for Plus members?")
    assert ans.sources and set(ans.sources) <= {c.source for c, _ in ans.hits}  # sirf retrieved docs cite hue
    assert "express shipping" in ans.text.lower()
    sent = llm.calls[0][-1].content
    assert "CONTEXT:" in sent and "QUESTION:" in sent and "(source: shipping.md)" in sent


def test_idk_without_calling_llm_when_nothing_relevant():
    llm = ScriptedLLM([])  # koi response nahi: call hua to test fail
    ans = build_rag(DATA, llm, get_embedder("local")).answer("Explain quantum chromodynamics lecture notes")
    assert ans.text == IDK and llm.calls == []
