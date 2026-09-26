**Language:** [Hinglish](TESTING.md) · English

# Hybrid Search + Rerank: how to run, test and tinker

Setup: from the repo root, `source .venv/bin/activate && pip install -e ".[all]"`.
Data: `data/docs.json` (14 docs: products with SKU codes, error codes, policies (2024 + 2025), blogs).

## 1. Side-by-side comparison (no key needed without --rerank)
```bash
python 04-rag/03-hybrid-search-rerank/main.py "E-1042"
python 04-rag/03-hybrid-search-rerank/main.py "refund window" --category policy --min-year 2025
python 04-rag/03-hybrid-search-rerank/main.py "earbuds not charging" --rerank --offline
```
Expected (refund window):
```
BM25    pol-refund
VECTOR  pol-shipping > pol-refund > pol-warranty
HYBRID  pol-refund > pol-shipping > pol-warranty      ◄── BM25 fixed the vector search's mistake
```
Below it, `hybrid detail` shows each doc's bm25 rank, vector rank and RRF score.

## 2. Real LLM reranker + real embeddings
```bash
# .env: LLM_MODEL=...   EMBED_MODEL=gemini:text-embedding-004 (or ollama:nomic-embed-text)
python 04-rag/03-hybrid-search-rerank/main.py "earphones won't charge" --rerank
python 04-rag/03-hybrid-search-rerank/main.py "why do my buds say E-1042" --rerank
```
With real embeddings, VECTOR should find `ts-charging` for "earphones won't charge", while BM25 may not (synonyms).

## 3. Offline tests
```bash
pytest 04-rag/03-hybrid-search-rerank -v
```
| Test | What it proves |
|---|---|
| `test_tokenizer_keeps_codes_together` | `e-1042`, `nk-4471` are one token |
| `test_bm25_idf_rare_term_wins_and_saturation` | IDF + tf saturation |
| `test_stemming_matches_plural` | without stemming "refund" ≠ "Refunds" |
| `test_rrf_rewards_agreement` | a doc in both lists goes to the top |
| `test_exact_code_query_found` | error code query |
| `test_metadata_filter` | the 2024 policy is filtered out |
| `test_hybrid_result_carries_both_ranks` | debug info |
| `test_llm_rerank_orders_and_ignores_bad_indices` | handles the LLM's invalid/duplicate indices |
| `test_offline_reranker_end_to_end` | the full retrieve→rerank |

## What to look for
- For which query does BM25 win, and for which does vector win? When is hybrid better than both?
- Did the filter remove a wrong-but-similar doc like the "old policy"?
- Did rerank change the order? Which docs does a real LLM **drop** (irrelevant)?

## Tinker with it
1. **Stemming off**: in `HybridRetriever`, use `BM25(docs, stem=False)` and run "refund window" again.
2. **RRF k**: `reciprocal_rank_fusion(..., k=1)` vs `k=1000`. How did the top results change? Small k = far too much weight on the top rank.
3. **Weighted fusion**: write a `weighted_fusion(bm, vec, alpha)` (with min-max normalisation). Compare alpha=0.2 vs 0.8 with RRF.
4. **New doc**: add "Error E-1043 means low battery" to `docs.json`. With real embeddings, does vector search rank E-1043 on top for the "E-1042" query? What about BM25?
5. **Pointwise rerank**: get a 0-10 score with a separate LLM call for each candidate. Compare the call count and results with listwise.
6. **Self-query**: build an `llm_json` step that extracts the filter `{"category": "policy", "year": 2025}` from the query "the 2025 refund policy".
