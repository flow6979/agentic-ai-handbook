import json
from pathlib import Path

import pytest

from agentkit import ScriptedLLM, get_embedder
from hybrid_search import (BM25, Doc, HybridRetriever, SearchResult, llm_rerank, load_docs, matches, offline_reranker,
                           reciprocal_rank_fusion, tokenize)

DATA = Path(__file__).parent / "data" / "docs.json"


@pytest.fixture(scope="module")
def retriever():
    return HybridRetriever(load_docs(DATA), get_embedder("local"))


def test_tokenizer_keeps_codes_together():
    assert tokenize("Error E-1042 on NK-4471") == ["error", "e-1042", "nk-4471"]


def test_bm25_idf_rare_term_wins_and_saturation():
    docs = [Doc("a", "earbuds earbuds earbuds earbuds"), Doc("b", "earbuds zeta"), Doc("c", "watch")]
    bm = BM25(docs)
    s = bm.scores("zeta")
    assert s[1] > 0 and s[0] == 0 and s[2] == 0
    one, four = BM25([Doc("x", "earbuds"), Doc("y", "earbuds earbuds earbuds earbuds"), Doc("z", "q")]).scores("earbuds")[:2]
    assert four < 4 * one  # tf saturation: 4x word != 4x score


def test_stemming_matches_plural():
    docs = [Doc("r", "Refunds are allowed within 30 days"), Doc("s", "Shipping is fast")]
    assert BM25(docs).scores("refund")[0] > 0
    assert BM25(docs, stem=False).scores("refund")[0] == 0  # bina stemming ke miss


def test_rrf_rewards_agreement():
    fused = dict(reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]]))
    assert fused["a"] == fused["b"] > fused["c"] == fused["d"]
    assert reciprocal_rank_fusion([["x"], ["y", "x"]])[0][0] == "x"  # dono lists mein = upar


def test_exact_code_query_found(retriever):
    assert retriever.search("E-1042", 1, "bm25")[0].doc.id == "ts-e1042"
    assert retriever.search("E-1042", 1, "hybrid")[0].doc.id == "ts-e1042"


def test_metadata_filter(retriever):
    assert matches({"year": 2025}, {"year": (">=", 2025)})
    assert not matches({"category": "blog"}, {"category": "policy"})
    assert matches({"category": "blog"}, lambda m: m["category"] in {"blog"})
    ids = [r.doc.id for r in retriever.search("refund days", 5, flt={"year": (">=", 2025)})]
    assert "pol-refund" in ids and "pol-refund-2024" not in ids


def test_hybrid_result_carries_both_ranks(retriever):
    top = retriever.search("NK-4471 battery life", 1)[0]
    assert top.doc.id == "prod-nk4471" and top.bm25_rank == 1 and top.vector_rank == 1


def test_llm_rerank_orders_and_ignores_bad_indices():
    res = [SearchResult(Doc(str(i), f"doc {i}"), 0.1) for i in range(3)]
    llm = ScriptedLLM([json.dumps({"ranking": [2, 2, 9, 0]})])
    assert [r.doc.id for r in llm_rerank(llm, "q", res, top_n=5)] == ["2", "0"]


def test_offline_reranker_end_to_end(retriever):
    cands = retriever.search("earbuds not charging", 8)
    top = llm_rerank(ScriptedLLM(offline_reranker), "earbuds not charging", cands, top_n=1)
    assert top[0].doc.id == "ts-charging"
