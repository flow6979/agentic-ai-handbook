# Hybrid Search + Reranking: concepts (Hinglish)

Project 01 ka retrieval sirf **vector search** tha. Production RAG mein yeh akela kaafi nahi hota.
Is project mein "advanced RAG" ka retrieval stack banate hain:

```
                       ┌───────── metadata PRE-FILTER (category=policy, year>=2025) ─────────┐
                       │                                                                     │
  "NK-4471 battery" ───┼──► BM25 (keyword)  ──► [nk4471, nk4470, e2001 ...] ──┐              │
                       │                                                      ├─► RRF fuse ──┼─► top 10-20
                       └──► Vector (meaning) ──► [nk4471, nk4470, nk3105 ...] ─┘              │     │
                                                                                             │     ▼
                                                                   LLM / cross-encoder RERANK ─► top 3-5 ──► LLM answer
```

## 1. Vector search akela kyun kaafi nahi?

Embeddings **meaning** pakadte hain, lekin **exact tokens** mein kamzor hain:

| Query | Vector search | Keyword (BM25) |
|---|---|---|
| "earphones won't charge" (doc mein "earbuds not charging") | ✅ synonyms samajhta hai | ❌ words match nahi |
| "E-1042" (error code) | ❌ "E-1042" aur "E-1043" ke vectors lagbhag same | ✅ exact match |
| "NK-4471" (SKU), naam, IDs, acronyms | ❌ weak | ✅ |
| Spelling mistake "refnd" | thoda bahut | ❌ |

Dono ki kamzoriyan ulti hain, isliye **dono chalao aur results jodo = hybrid search**.

> Note: is repo ka `local` embedder bhi hashing (word-based) hai, isliye offline mode mein BM25 aur vector
> ke results lagbhag same dikhte hain. Asli fark dekhne ke liye `EMBED_MODEL` mein real model lagao
> aur "earphones won't charge" try karo.

## 2. BM25: keyword search ka king

Elasticsearch, OpenSearch, Lucene sab ka default ranking. Formula scary lagta hai, idea simple hai:

```
score(query, doc) = Σ  IDF(word) × TF-part(word, doc)
                  har query word

IDF  = word kitna RARE hai?        "nk-4471" (1 doc mein)  → high
                                   "earbuds" (5 docs mein) → low
TF   = doc mein word kitni baar?   lekin SATURATE hota hai (k1):
                                   1 baar → 1.0, 2 baar → 1.4, 10 baar → 2.2 (10 nahi)
LEN  = lamba doc? thoda penalty (b), warna lamba doc har query pe jeet jaata
```

Implementation `BM25` class mein ~20 lines hai. Do chhoti cheezein jo bahut matter karti hain:
- **Tokenization**: `nk-4471` ko ek token rakho (`_TOKEN` regex), warna "nk" aur "4471" alag ho jaate hain
- **Stemming**: "refunds" → "refund". `light_stem()` ke bina query "refund window" pe BM25 **kuch nahi** deta
  (demo mein `--category policy` ke saath chala ke dekho). Real mein Porter/Snowball stemmer ya lemmatizer
- **Stopwords**: "the", "is", "how" hata do, varna noise

## 3. Fusion: do rankings kaise jodein? → RRF

Galat tareeka: `bm25_score + cosine_score`. BM25 ke scores 0–15, cosine ke 0–1 hote hain, isliye
BM25 hamesha dominate karega. Scores ko normalise karna bhi fragile hai.

**Reciprocal Rank Fusion (RRF)** sirf **rank** dekhta hai:
```
RRF(doc) = Σ  1 / (60 + rank_in_list)

             BM25 rank   Vector rank    RRF
 nk4471         1            1         1/61 + 1/61 = 0.0328   ◄── dono ne upar rakha = winner
 e2001          3            -         1/63        = 0.0159
 nk3105         -            3         1/63        = 0.0159
```
- Jo doc **dono lists** mein hai, woh upar aata hai (agreement = confidence)
- `k=60` paper ka default: rank 1 aur rank 2 ka fark bahut bada nahi banne deta
- Koi tuning nahi, koi score calibration nahi, isliye industry default hai

Alternative: **weighted score fusion** (`α·vector + (1-α)·bm25` after min-max normalisation), jo tunable hai lekin fragile.

## 4. Reranking: second opinion

Retrieval (BM25/vector) **fast but shallow** hai. Query aur doc ko alag-alag encode karta hai
(**bi-encoder**), aur fir sirf vectors compare karta hai. Reranker query + doc ko **saath padhta hai**:

```
 BI-ENCODER (retrieval)                    CROSS-ENCODER / LLM (rerank)
 query ──► [enc] ──► q_vec ─┐              [query + doc saath] ──► [model] ──► relevance 0.93
 doc   ──► [enc] ──► d_vec ─┴─ cosine
 + docs pehle se encode, millions pe fast   + zyada accurate (words ka interaction dekhta hai)
 - nuance miss                              - har (query, doc) pair pe model call: slow/mehenga
```
Isliye **two-stage**: retrieval se top 20–50 lo (sasta), reranker se top 3–5 chuno (accurate).

Rerankers ke types:
| Type | Example | Note |
|---|---|---|
| Cross-encoder model | `bge-reranker`, `ms-marco-MiniLM`, Cohere Rerank, Jina Reranker | Purpose-built, fast, cheap |
| **LLM pointwise** | har doc pe "relevant? 0-10" | Simple, N calls |
| **LLM listwise** (yahan) | saare candidates ek prompt mein, "order batao" | 1 call, docs compare ho jaate hain; lambi list pe position bias |
| LLM pairwise | "A better hai ya B?" | Accurate, bahut calls |

`llm_rerank()` LLM ke output ko **validate** karta hai: out-of-range index, duplicate index hata deta hai.
LLM output pe kabhi blind trust mat karo.

## 5. Metadata filtering

Har chunk ke saath metadata rakho: `category`, `year`, `department`, `language`, `access_level`, `product`.
```
 "refund policy?" + filter year>=2025   ──► purani 2024 policy (15 days) aayegi hi nahi
```
- **Pre-filter** (yahan): pehle filter, phir search. Accurate, lekin bahut strict filter se kam candidates
- **Post-filter**: pehle top-k search, phir filter. Fast lekin 0 results aa sakte hain
- **Security**: multi-tenant apps mein `tenant_id` / `access_level` filter **mandatory** hai, varna user A ko user B ke docs dikh jaayenge
- Filter kaun banata hai? User UI se, ya LLM query se nikaale (**self-query retriever**: "2025 ki policy" → `{year: 2025}`)

## Kab kya

| Situation | Use |
|---|---|
| Chhota, natural-language FAQ | Vector hi kaafi |
| Codes, SKUs, names, legal/medical terms | Hybrid zaroor |
| Precision bahut important (support bot, legal) | Hybrid + rerank |
| Latency budget bahut tight (<100ms) | Rerank skip ya chhota cross-encoder |
| Multi-tenant / versioned docs | Metadata filter mandatory |

## Is project mein kaise use ho raha hai

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
