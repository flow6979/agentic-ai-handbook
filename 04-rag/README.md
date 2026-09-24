# 04 · RAG: agent ko user ka data (text, PDFs, docs) kaise dein

LLM ko tumhari company ki policy, tumhari PDF, tumhare notes nahi pata. Is section mein seekhoge ki agent
**user-provided data** se kaise kaam karta hai, zyada tar **RAG (Retrieval-Augmented Generation)** se:
pehle relevant tukde dhoondo, phir unhe prompt mein daal ke LLM se jawab likhwao.

```
  user data (md, txt, pdf, ...)                       sawaal
          │                                              │
          ▼                                              ▼
   load → chunk → embed → store  ═══════════►  retrieve top-k ──► prompt(context + sawaal) ──► LLM ──► jawab [source]
        (indexing, ek baar)                          (har query pe)
```

## RAG ke types (map)

```
                                    ┌─────────────────────────┐
                                    │        NAIVE RAG        │  retrieve → stuff → generate
                                    │   (01-rag-basics)       │  fixed pipeline, ek query
                                    └────────────┬────────────┘
                                                 │ quality problems
                                                 ▼
 ┌──────────────────────────────────── ADVANCED RAG ────────────────────────────────────┐
 │  PRE-retrieval                    RETRIEVAL                    POST-retrieval         │
 │  • better chunking (01)           • hybrid BM25+vector (03)    • rerank (03)          │
 │  • metadata (03)                  • metadata filters (03)      • context compression  │
 │  • query rewrite/condense (02,05) • persistent index (04)      • citations (01,02)    │
 └────────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ pieces ko lego blocks ki tarah jodo
                                          ▼
                             ┌──────────────────────────┐
                             │       MODULAR RAG        │  router, multiple KBs, swappable steps
                             └────────────┬─────────────┘
                                          │ LLM khud decide kare
                     ┌────────────────────┼─────────────────────┐
                     ▼                    ▼                     ▼
          ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
          │   AGENTIC RAG    │ │  CORRECTIVE RAG    │ │      SELF-RAG        │
          │ retrieval = tool │ │ grade docs; bad?   │ │ model decides when to│
          │ agent decides    │ │ rewrite / fallback │ │ retrieve + critiques │
          │ (05)             │ │ (05)               │ │ own answer (05-ish)  │
          └──────────────────┘ └────────────────────┘ └──────────────────────┘

   Aur types (concept only, neeche "Baaki reh gaye" dekho):
   • GRAPH RAG      : entities + relations ka knowledge graph; "X aur Y kaise connected?" jaise sawaal
   • ADAPTIVE RAG   : sawaal ki complexity dekh ke no-retrieval / single / multi-step chuno
   • MULTIMODAL RAG : images, tables, charts bhi retrieve karo
   • HyDE / multi-query / step-back : query transformation variants

 Har jagah: EVALUATION (06). Bina naape "better" mat bolo.
```

## Projects (is order mein karo)

| # | Project | Kya seekhoge | Offline demo |
|---|---|---|---|
| 01 | [rag-basics](01-rag-basics/) | Poora pipeline by hand: 3 chunkers, embeddings, cosine, top-k, citations, "I don't know" gate | `python 04-rag/01-rag-basics/main.py --offline --show-chunks` |
| 02 | [pdf-chat](02-pdf-chat/) | PDF extraction (pypdf), page citations, scanned-PDF/OCR, tables, chat memory + query condensation | `python 04-rag/02-pdf-chat/main.py chat --offline` |
| 03 | [hybrid-search-rerank](03-hybrid-search-rerank/) | BM25 from scratch, RRF fusion, LLM rerank, cross-encoders, metadata filters | `python 04-rag/03-hybrid-search-rerank/main.py "E-1042"` |
| 04 | [vector-store-persistence](04-vector-store-persistence/) | SQLite vector store, incremental ingest (hashing), embedder consistency, HNSW, vector DB comparison | `python 04-rag/04-vector-store-persistence/main.py ingest` |
| 05 | [agentic-rag](05-agentic-rag/) | Retrieval-as-tool agent, KB routing, decomposition, rewrite, corrective grading, groundedness check | `python 04-rag/05-agentic-rag/main.py "How many vacation days do I get?" --offline` |
| 06 | [rag-evaluation](06-rag-evaluation/) | hit@k, MRR, recall, LLM-as-judge (faithfulness, relevance, correctness), config comparison | `python 04-rag/06-rag-evaluation/main.py retrieval` |

Har project mein: `CONCEPTS.md` (theory + diagrams + code mapping) aur `TESTING.md` (run, test, tinker).
Sab tests offline chalte hain: `pytest 04-rag`.

Real LLM / embeddings: repo root `.env` mein `LLM_MODEL=...` aur `EMBED_MODEL=...` (default `local` =
offline hashing embedder, jo meaning nahi samajhta; real kaam ke liye `gemini:text-embedding-004`,
`openai:text-embedding-3-small` ya `ollama:nomic-embed-text` lo).

## RAG ke alawa: agent ko user data dene ke aur tareeke

RAG hi akela jawab nahi hai. Situation dekh ke choose karo:

```
                         user ka data kaisa hai?
                                   │
       ┌──────────────┬────────────┼──────────────┬─────────────────┐
       ▼              ▼            ▼              ▼                 ▼
   chhota          bada,        structured     behaviour /       images, scans,
  (<~100 pages)    unstructured (tables, DB)   style seekhna     audio
       │              │            │              │                 │
  LONG-CONTEXT       RAG        TOOLS / SQL    FINE-TUNING       MULTIMODAL
   STUFFING                     (text-to-SQL)                    (vision LLM / OCR)
```

| Tareeka | Kaise | Kab | Kab nahi |
|---|---|---|---|
| **Long-context stuffing** | Poora doc prompt mein (aaj ke models 128k-1M+ tokens le lete hain) | Ek chhota contract/PDF, "poore doc ka summary" jaise sawaal jahan har hissa chahiye | Bahut saare docs, har query pe cost (har baar saare tokens), bade context mein beech ki info miss hoti hai ("lost in the middle"); **prompt caching** cost kam karta hai |
| **RAG** (yeh section) | Relevant chunks retrieve karke prompt mein | Bade/badalte knowledge base, citations chahiye | Aggregation ("kitne orders > 5000?"), poore doc ki reasoning |
| **Tools over structured data** | Agent ko `run_sql(query)` / API tool do. **Text-to-SQL**: LLM sawaal se SQL likhe, DB exact answer de | Numbers, filters, joins, "last month ka revenue" | Free text; SQL tool ko **read-only** DB user + row limits do (security!) |
| **Fine-tuning** | Model ko apne examples pe train karo | Style, format, domain jargon, classification | Facts sikhane ke liye nahi (update mushkil, hallucinate phir bhi karta hai, citations nahi) |
| **Structured extraction** | LLM se doc ko JSON mein nikaalo (invoice → `{amount, date, vendor}`), phir DB mein | Forms, invoices, resumes | Open-ended Q&A |
| **Multimodal input** | Image/scan/screenshot seedha vision-LLM ko do, ya OCR karke text | Scanned PDFs, charts, photos, handwritten | Jab text layer already achhi ho (sasta rasta lo) |

Aksar **combination** hota hai: RAG for policies + SQL tool for order data + vision for uploaded receipts.

### File upload handling (production checklist)
Jab user app mein file upload kare:
1. **Validate**: type (magic bytes, sirf extension nahi), size limit, page limit, virus scan
2. **Parse** by type: PDF (pypdf / OCR fallback), DOCX, HTML (tags hatao), CSV (tool/SQL better), images (vision/OCR)
3. **Isolate per user/tenant**: har chunk ke saath `owner_id` metadata, har search pe filter (project 03)
4. **Async ingestion**: badi file pe background job + progress status, request block mat karo
5. **Prompt injection**: uploaded doc mein "ignore previous instructions..." likha ho sakta hai. Doc content ko
   **data** treat karo, instructions nahi. System prompt mein bolo, aur tools ko limited permissions do
6. **Retention**: user delete kare to chunks + vectors bhi delete (project 04 ka delete sync)

## Baaki reh gaye (next time dekh sakte hain)
- **GraphRAG / knowledge graphs**: entity extraction, community summaries, multi-hop questions
- **Contextual retrieval / parent-child chunks / late chunking**: sirf concept mein cover hue
- **HyDE, multi-query, step-back prompting**: tinker exercises mein, implement nahi
- **Real cross-encoder reranker** (bge-reranker) aur **real vector DB** (Chroma/pgvector/Qdrant) integration
- **Text-to-SQL agent** aur **multimodal RAG** (images/tables) ka hands-on project
- **Streaming answers** aur UI mein clickable citations
