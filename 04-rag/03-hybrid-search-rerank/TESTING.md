**Language:** Hinglish · [English](TESTING.en.md)

# Hybrid Search + Rerank: kaise chalayein, test karein, tinker karein

Setup: repo root se `source .venv/bin/activate && pip install -e ".[all]"`.
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
HYBRID  pol-refund > pol-shipping > pol-warranty      ◄── BM25 ne vector ki galti sudhaari
```
Neeche `hybrid detail` mein har doc ka bm25 rank, vector rank aur RRF score dikhta hai.

## 2. Real LLM reranker + real embeddings
```bash
# .env: LLM_MODEL=...   EMBED_MODEL=gemini:text-embedding-004 (ya ollama:nomic-embed-text)
python 04-rag/03-hybrid-search-rerank/main.py "earphones won't charge" --rerank
python 04-rag/03-hybrid-search-rerank/main.py "why do my buds say E-1042" --rerank
```
Real embeddings ke saath "earphones won't charge" pe VECTOR ko `ts-charging` milna chahiye, jabki BM25 ko shayad na mile (synonyms).

## 3. Offline tests
```bash
pytest 04-rag/03-hybrid-search-rerank -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_tokenizer_keeps_codes_together` | `e-1042`, `nk-4471` ek token |
| `test_bm25_idf_rare_term_wins_and_saturation` | IDF + tf saturation |
| `test_stemming_matches_plural` | stemming ke bina "refund" ≠ "Refunds" |
| `test_rrf_rewards_agreement` | dono lists wala doc upar |
| `test_exact_code_query_found` | error code query |
| `test_metadata_filter` | 2024 policy filter se bahar |
| `test_hybrid_result_carries_both_ranks` | debug info |
| `test_llm_rerank_orders_and_ignores_bad_indices` | LLM ke invalid/duplicate index handle |
| `test_offline_reranker_end_to_end` | poora retrieve→rerank |

## Kya dekhna hai
- Kis query pe BM25 jeet'ta hai, kis pe vector? Hybrid kab dono se better hai?
- Filter lagane se "purani policy" jaisa galat-lekin-similar doc hata?
- Rerank ne order badla? Real LLM kaunse docs **drop** karta hai (irrelevant)?

## Tinker karo
1. **Stemming off**: `HybridRetriever` mein `BM25(docs, stem=False)` karo, "refund window" dobara chalao.
2. **RRF k**: `reciprocal_rank_fusion(..., k=1)` vs `k=1000`. Top results kaise badle? k chhota = top rank ka bahut zyada weight.
3. **Weighted fusion**: ek `weighted_fusion(bm, vec, alpha)` likho (min-max normalise karke). alpha=0.2 vs 0.8 compare karo RRF se.
4. **Naya doc**: `docs.json` mein "Error E-1043 means low battery" jodo. Real embeddings ke saath "E-1042" query pe vector search E-1043 ko upar rakhta hai? BM25?
5. **Pointwise rerank**: har candidate ke liye alag LLM call se 0-10 score lo. Calls count aur result compare karo listwise se.
6. **Self-query**: ek `llm_json` step banao jo query "2025 ki refund policy" se `{"category": "policy", "year": 2025}` filter nikaale.
