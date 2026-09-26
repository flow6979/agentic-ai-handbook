**Language:** [Hinglish](CONCEPTS.md) · English

# Hybrid Search + Reranking: concepts (English)

Project 01's retrieval was only **vector search**. In production RAG that alone is not enough.
In this project we build the retrieval stack of "advanced RAG":

```
                       ┌───────── metadata PRE-FILTER (category=policy, year>=2025) ─────────┐
                       │                                                                     │
  "NK-4471 battery" ───┼──► BM25 (keyword)  ──► [nk4471, nk4470, e2001 ...] ──┐              │
                       │                                                      ├─► RRF fuse ──┼─► top 10-20
                       └──► Vector (meaning) ──► [nk4471, nk4470, nk3105 ...] ─┘              │     │
                                                                                             │     ▼
                                                                   LLM / cross-encoder RERANK ─► top 3-5 ──► LLM answer
```

## 1. Why is vector search alone not enough?

Embeddings capture **meaning**, but they are weak on **exact tokens**:

| Query | Vector search | Keyword (BM25) |
|---|---|---|
| "earphones won't charge" (doc says "earbuds not charging") | ✅ understands synonyms | ❌ words do not match |
| "E-1042" (error code) | ❌ vectors of "E-1042" and "E-1043" are almost the same | ✅ exact match |
| "NK-4471" (SKU), names, IDs, acronyms | ❌ weak | ✅ |
| Spelling mistake "refnd" | somewhat | ❌ |

Their weaknesses are opposite, so **run both and combine the results = hybrid search**.

> Note: this repo's `local` embedder is also hashing (word-based), so in offline mode the BM25 and vector
> results look almost the same. To see the real difference, set a real model in `EMBED_MODEL`
> and try "earphones won't charge".

## 2. BM25: the king of keyword search

The default ranking in Elasticsearch, OpenSearch and Lucene. The formula looks scary, the idea is simple:

```
score(query, doc) = Σ  IDF(word) × TF-part(word, doc)
                  every query word

IDF  = how RARE is the word?       "nk-4471" (in 1 doc)    → high
                                   "earbuds" (in 5 docs)   → low
TF   = how often in the doc?       but it SATURATES (k1):
                                   1 time → 1.0, 2 times → 1.4, 10 times → 2.2 (not 10)
LEN  = long doc? a small penalty (b), otherwise long docs would win every query
```

The implementation in the `BM25` class is ~20 lines. Small things that matter a lot:
- **Tokenization**: keep `nk-4471` as one token (the `_TOKEN` regex), otherwise "nk" and "4471" split apart
- **Stemming**: "refunds" → "refund". Without `light_stem()`, BM25 returns **nothing** for the query "refund window"
  (run the demo with `--category policy` to see it). In real systems use a Porter/Snowball stemmer or a lemmatizer
- **Stopwords**: remove "the", "is", "how", otherwise they add noise

## 3. Fusion: how do we combine two rankings? → RRF

The wrong way: `bm25_score + cosine_score`. BM25 scores are 0–15 and cosine scores are 0–1, so
BM25 will always dominate. Normalising the scores is also fragile.

**Reciprocal Rank Fusion (RRF)** only looks at the **rank**:
```
RRF(doc) = Σ  1 / (60 + rank_in_list)

             BM25 rank   Vector rank    RRF
 nk4471         1            1         1/61 + 1/61 = 0.0328   ◄── both put it on top = winner
 e2001          3            -         1/63        = 0.0159
 nk3105         -            3         1/63        = 0.0159
```
- A doc in **both lists** rises to the top (agreement = confidence)
- `k=60` is the paper's default: it keeps the gap between rank 1 and rank 2 from getting too big
- No tuning, no score calibration, which is why it is the industry default

Alternative: **weighted score fusion** (`α·vector + (1-α)·bm25` after min-max normalisation), which is tunable but fragile.

## 4. Reranking: a second opinion

Retrieval (BM25/vector) is **fast but shallow**. It encodes the query and the doc separately
(a **bi-encoder**) and then only compares vectors. A reranker **reads the query + doc together**:

```
 BI-ENCODER (retrieval)                    CROSS-ENCODER / LLM (rerank)
 query ──► [enc] ──► q_vec ─┐              [query + doc together] ──► [model] ──► relevance 0.93
 doc   ──► [enc] ──► d_vec ─┴─ cosine
 + docs encoded in advance, fast on millions + more accurate (sees how words interact)
 - misses nuance                            - one model call per (query, doc) pair: slow/expensive
```
So it is **two-stage**: take the top 20–50 from retrieval (cheap), pick the top 3–5 with the reranker (accurate).

Types of rerankers:
| Type | Example | Note |
|---|---|---|
| Cross-encoder model | `bge-reranker`, `ms-marco-MiniLM`, Cohere Rerank, Jina Reranker | Purpose-built, fast, cheap |
| **LLM pointwise** | "relevant? 0-10" for each doc | Simple, N calls |
| **LLM listwise** (here) | all candidates in one prompt, "give me the order" | 1 call, docs get compared; position bias on long lists |
| LLM pairwise | "is A better or B?" | Accurate, many calls |

`llm_rerank()` **validates** the LLM's output: it drops out-of-range and duplicate indices.
Never blindly trust LLM output.

## 5. Metadata filtering

Keep metadata with every chunk: `category`, `year`, `department`, `language`, `access_level`, `product`.
```
 "refund policy?" + filter year>=2025   ──► the old 2024 policy (15 days) never shows up
```
- **Pre-filter** (here): filter first, then search. Accurate, but a very strict filter leaves few candidates
- **Post-filter**: search top-k first, then filter. Fast, but you can end up with 0 results
- **Security**: in multi-tenant apps a `tenant_id` / `access_level` filter is **mandatory**, otherwise user A will see user B's docs
- Who builds the filter? The user from the UI, or the LLM extracts it from the query (**self-query retriever**: "the 2025 policy" → `{year: 2025}`)

## When to use what

| Situation | Use |
|---|---|
| Small, natural-language FAQ | Vector alone is enough |
| Codes, SKUs, names, legal/medical terms | Definitely hybrid |
| Precision is very important (support bot, legal) | Hybrid + rerank |
| Very tight latency budget (<100ms) | Skip rerank or use a small cross-encoder |
| Multi-tenant / versioned docs | Metadata filter is mandatory |

## How this project uses it

| Concept | File / function |
|---|---|
| Tokenizer (codes intact), stopwords | `hybrid_search.py` → `tokenize()`, `STOPWORDS` |
| Stemming | `light_stem()`, `BM25(stem=True)` |
| BM25 from scratch (IDF, tf saturation, length norm) | `BM25.scores()` |
| Vector ranking | `VectorIndex` |
| RRF fusion | `reciprocal_rank_fusion()` |
| Metadata pre-filter (equality, >=, in, callable) | `matches()`, `HybridRetriever.search(flt=...)` |
| Per-result debug (bm25 rank, vector rank) | `SearchResult` |
| LLM listwise rerank + output validation | `llm_rerank()`, `Rerank` schema, `RERANK_PROMPT` |
| Offline fake reranker | `offline_reranker()` |
| Side-by-side comparison CLI | `main.py` |
