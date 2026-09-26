**Language:** [Hinglish](README.md) · English

# 04 · RAG: how to give an agent the user's data (text, PDFs, docs)

The LLM does not know your company's policy, your PDF or your notes. In this section you will learn how an agent
works with **user-provided data**, mostly through **RAG (Retrieval-Augmented Generation)**:
first find the relevant pieces, then put them in the prompt and have the LLM write the answer.

```
  user data (md, txt, pdf, ...)                       question
          │                                              │
          ▼                                              ▼
   load → chunk → embed → store  ═══════════►  retrieve top-k ──► prompt(context + question) ──► LLM ──► answer [source]
        (indexing, once)                             (on every query)
```

## Types of RAG (map)

```
                                    ┌─────────────────────────┐
                                    │        NAIVE RAG        │  retrieve → stuff → generate
                                    │   (01-rag-basics)       │  fixed pipeline, one query
                                    └────────────┬────────────┘
                                                 │ quality problems
                                                 ▼
 ┌──────────────────────────────────── ADVANCED RAG ────────────────────────────────────┐
 │  PRE-retrieval                    RETRIEVAL                    POST-retrieval         │
 │  • better chunking (01)           • hybrid BM25+vector (03)    • rerank (03)          │
 │  • metadata (03)                  • metadata filters (03)      • context compression  │
 │  • query rewrite/condense (02,05) • persistent index (04)      • citations (01,02)    │
 └────────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ combine the pieces like lego blocks
                                          ▼
                             ┌──────────────────────────┐
                             │       MODULAR RAG        │  router, multiple KBs, swappable steps
                             └────────────┬─────────────┘
                                          │ let the LLM decide
                     ┌────────────────────┼─────────────────────┐
                     ▼                    ▼                     ▼
          ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
          │   AGENTIC RAG    │ │  CORRECTIVE RAG    │ │      SELF-RAG        │
          │ retrieval = tool │ │ grade docs; bad?   │ │ model decides when to│
          │ agent decides    │ │ rewrite / fallback │ │ retrieve + critiques │
          │ (05)             │ │ (05)               │ │ own answer (05-ish)  │
          └──────────────────┘ └────────────────────┘ └──────────────────────┘

   More types (concept only, see "Left for later" below):
   • GRAPH RAG      : knowledge graph of entities + relations; questions like "how are X and Y connected?"
   • ADAPTIVE RAG   : look at question complexity and pick no-retrieval / single / multi-step
   • MULTIMODAL RAG : retrieve images, tables and charts too
   • HyDE / multi-query / step-back : query transformation variants

 Everywhere: EVALUATION (06). Never say "better" without measuring.
```

## Projects (do them in this order)

| # | Project | What you will learn | Offline demo |
|---|---|---|---|
| 01 | [rag-basics](01-rag-basics/) | The whole pipeline by hand: 3 chunkers, embeddings, cosine, top-k, citations, "I don't know" gate | `python 04-rag/01-rag-basics/main.py --offline --show-chunks` |
| 02 | [pdf-chat](02-pdf-chat/) | PDF extraction (pypdf), page citations, scanned-PDF/OCR, tables, chat memory + query condensation | `python 04-rag/02-pdf-chat/main.py chat --offline` |
| 03 | [hybrid-search-rerank](03-hybrid-search-rerank/) | BM25 from scratch, RRF fusion, LLM rerank, cross-encoders, metadata filters | `python 04-rag/03-hybrid-search-rerank/main.py "E-1042"` |
| 04 | [vector-store-persistence](04-vector-store-persistence/) | SQLite vector store, incremental ingest (hashing), embedder consistency, HNSW, vector DB comparison | `python 04-rag/04-vector-store-persistence/main.py ingest` |
| 05 | [agentic-rag](05-agentic-rag/) | Retrieval-as-tool agent, KB routing, decomposition, rewrite, corrective grading, groundedness check | `python 04-rag/05-agentic-rag/main.py "How many vacation days do I get?" --offline` |
| 06 | [rag-evaluation](06-rag-evaluation/) | hit@k, MRR, recall, LLM-as-judge (faithfulness, relevance, correctness), config comparison | `python 04-rag/06-rag-evaluation/main.py retrieval` |

Every project has: `CONCEPTS.en.md` (theory + diagrams + code mapping) and `TESTING.en.md` (run, test, tinker).
All tests run offline: `pytest 04-rag`.

Real LLM / embeddings: set `LLM_MODEL=...` and `EMBED_MODEL=...` in the repo root `.env` (the default `local` =
offline hashing embedder, which does not understand meaning; for real work use `gemini:text-embedding-004`,
`openai:text-embedding-3-small` or `ollama:nomic-embed-text`).

## Beyond RAG: other ways to give an agent user data

RAG is not the only answer. Choose based on the situation:

```
                         what does the user's data look like?
                                   │
       ┌──────────────┬────────────┼──────────────┬─────────────────┐
       ▼              ▼            ▼              ▼                 ▼
     small          large,      structured     learn behaviour /  images, scans,
  (<~100 pages)   unstructured  (tables, DB)   style              audio
       │              │            │              │                 │
  LONG-CONTEXT       RAG        TOOLS / SQL    FINE-TUNING       MULTIMODAL
   STUFFING                     (text-to-SQL)                    (vision LLM / OCR)
```

| Approach | How | When | When not |
|---|---|---|---|
| **Long-context stuffing** | Put the whole doc in the prompt (today's models accept 128k-1M+ tokens) | One small contract/PDF, questions like "summarize the whole doc" where every part matters | Many docs, cost on every query (all tokens every time), info in the middle of a big context gets missed ("lost in the middle"); **prompt caching** reduces the cost |
| **RAG** (this section) | Retrieve relevant chunks and put them in the prompt | Large/changing knowledge base, citations needed | Aggregation ("how many orders > 5000?"), reasoning over the whole doc |
| **Tools over structured data** | Give the agent a `run_sql(query)` / API tool. **Text-to-SQL**: the LLM writes SQL from the question, the DB gives the exact answer | Numbers, filters, joins, "last month's revenue" | Free text; give the SQL tool a **read-only** DB user + row limits (security!) |
| **Fine-tuning** | Train the model on your own examples | Style, format, domain jargon, classification | Not for teaching facts (hard to update, it still hallucinates, no citations) |
| **Structured extraction** | Have the LLM turn the doc into JSON (invoice → `{amount, date, vendor}`), then store it in a DB | Forms, invoices, resumes | Open-ended Q&A |
| **Multimodal input** | Give the image/scan/screenshot directly to a vision LLM, or OCR it to text | Scanned PDFs, charts, photos, handwriting | When the text layer is already good (take the cheaper route) |

Often it is a **combination**: RAG for policies + a SQL tool for order data + vision for uploaded receipts.

### File upload handling (production checklist)
When a user uploads a file in the app:
1. **Validate**: type (magic bytes, not just the extension), size limit, page limit, virus scan
2. **Parse** by type: PDF (pypdf / OCR fallback), DOCX, HTML (strip tags), CSV (a tool/SQL is better), images (vision/OCR)
3. **Isolate per user/tenant**: `owner_id` metadata on every chunk, filter on every search (project 03)
4. **Async ingestion**: for big files use a background job + progress status, do not block the request
5. **Prompt injection**: an uploaded doc may contain "ignore previous instructions...". Treat doc content as
   **data**, not instructions. Say so in the system prompt, and give tools limited permissions
6. **Retention**: when the user deletes a file, delete its chunks + vectors too (project 04's delete sync)

## Left for later (we can cover these next time)
- **GraphRAG / knowledge graphs**: entity extraction, community summaries, multi-hop questions
- **Contextual retrieval / parent-child chunks / late chunking**: covered only as concepts
- **HyDE, multi-query, step-back prompting**: in the tinker exercises, not implemented
- **Real cross-encoder reranker** (bge-reranker) and **real vector DB** (Chroma/pgvector/Qdrant) integration
- Hands-on projects for a **text-to-SQL agent** and **multimodal RAG** (images/tables)
- **Streaming answers** and clickable citations in a UI
