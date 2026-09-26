**Language:** [Hinglish](CONCEPTS.md) · English

# Vector Store Persistence + Incremental Ingestion: concepts (English)

Project 01's vector store lived **in RAM**: when the program stopped everything was gone, and on every start all docs
were **embedded again** (money + time on a paid API). Production needs:

1. **Persistence**: the index stays on disk, even after a restart
2. **Incremental ingestion**: only new/changed docs get embedded, and removed docs are removed from the index too
3. **Consistency**: vectors from the wrong embedder never get mixed in

## Flow

```
            ┌────────────── ingest_folder(data/) ──────────────┐
            │                                                  │
 each file ─┼─► sha256(content) ──► same hash in the DB?        │
            │                         │                        │
            │           yes ◄─────────┴────────► no            │
            │           │                         │            │
            │      "unchanged"             chunk + embed        │
            │      (0 API calls)           TRANSACTION:         │
            │                                delete old chunks  │
            │                                upsert document    │
            │                                insert new chunks  │
            │                              "added"/"updated"    │
            │                                                  │
  in the DB but not in the folder? ──► delete (chunks CASCADE) "deleted"
            └──────────────────────────────────────────────────┘

  search(query) ──► embed query ──► SELECT embeddings (WHERE filter) ──► cosine against all ──► top-k
```

## 1. How do we store vectors?

| Format | Size (512 dims) | Note |
|---|---|---|
| JSON text `[0.12, -0.4, ...]` | ~5-6 KB | Readable, slow to parse |
| **float32 BLOB** (here) | 2 KB | `array("f").tobytes()`, compact and fast |
| float16 / int8 quantized | 1 KB / 512 B | Used in real DBs, a little accuracy loss |
| Binary quantization | 64 B | Very fast pre-filter, then re-score |

## 2. Schema

```
 meta        (embedder="local", dim=512)          ◄── safety check
 documents   (doc_id, content_hash, chunk_count, updated_at)
 chunks      (id, doc_id → documents ON DELETE CASCADE, position, text, metadata JSON, embedding BLOB)
```
- The `documents` table is the "memory" of incremental sync: which file was indexed with which hash
- `ON DELETE CASCADE`: when a document is removed its chunks go away automatically (no orphan chunks left)

## 3. Incremental ingestion: content hashing

```
 Day 1: 5 files ─► 5 added, 8 chunks embedded
 Day 2: same     ─► 5 unchanged, 0 embedded           ◄── this is what saves money
 Day 3: shipping.md edited, refund_policy.md deleted
                 ─► updated=[shipping.md], deleted=[refund_policy.md]
```
Details that matter in production:
- **Hash content, not mtime**: "touching" a file changes the mtime, not the content
- **Doc-level vs chunk-level**: here, when a doc changes all its chunks get re-embedded. Better: keep a hash per chunk
  and re-embed only the changed chunks (a big win for large docs)
- **Transaction**: delete-old + insert-new in one transaction (`with self.db:`), otherwise a crash leaves the doc half indexed
- **Forgetting deletes** is the most common bug: a removed policy keeps getting retrieved and the bot gives outdated info

## 4. Embedder consistency

Every embedding model has its own "vector space". Comparing model A's vectors with a query from model B
= garbage results, without any error! So we save the embedder name + dim in the `meta` table
and raise a **hard error** on mismatch ("Re-index into a new DB"). Upgrading the model = a **full re-index** (build it in a new DB/collection,
then switch = blue/green re-indexing).

## 5. Brute force vs ANN (Approximate Nearest Neighbour)

Here search = load all vectors and compute cosine against each = **O(N)**.
```
 10k chunks    → ~ms,  totally fine
 1M chunks     → 1M cosines per query = slow + RAM heavy
 100M chunks   → impossible
```
Real vector DBs use an **ANN index**: give up a little accuracy for a lot of speed.

**HNSW (Hierarchical Navigable Small World)**, the most popular:
```
 Layer 2:  A ─────────────── F                 (very few nodes, long jumps)
           │                 │
 Layer 1:  A ──── C ──── E ─ F ──── H          (more nodes)
           │      │      │   │      │
 Layer 0:  A─B─C─D─E─F─G─H─I─J ...             (all nodes, short jumps)

 Search: start at the top, on each layer jump to the neighbour closest to the query,
         go down a layer, repeat. Like going from the highway to your street. ~O(log N)
```
Other ANN types: **IVF** (split vectors into clusters, search only the nearby clusters),
**PQ** (compress vectors), **ScaNN**, **DiskANN** (disk-based, huge data).
The trade-off knobs: recall (did we find the right neighbours?) vs latency vs memory.

## 6. Real vector DBs: comparison

| DB | Type | When to use | Note |
|---|---|---|---|
| **FAISS** | Library (in-process) | Research, batch jobs, custom infra | From Meta; super fast; you handle persistence/filtering yourself |
| **Chroma** | Embedded / server | Prototypes, local apps | `pip install`, feels like SQLite; simple API |
| **pgvector** | Postgres extension | You already have Postgres; you need SQL joins + filters + transactions | HNSW/IVFFlat index; app data + vectors in one DB |
| **Qdrant** | Dedicated server (Rust) | Production, heavy metadata filtering | Strong payload filters, quantization, self-host or cloud |
| **Pinecone** | Managed SaaS | You do not want to run ops, you need scale | Serverless, paid; vendor lock-in |
| **Weaviate / Milvus** | Dedicated server | Large scale, hybrid search built in | Milvus is for billions of vectors |
| **Elasticsearch / OpenSearch** | Search engine + vectors | BM25 + vector hybrid in one place | Good if you already run ES |
| **SQLite + sqlite-vec** | Embedded extension | Edge/mobile/local apps | The "grown-up" version of this project |

Questions for choosing:
1. How many vectors? (<100k: anything works, even brute force)
2. How important are filters? (multi-tenant → strong filtering)
3. Which DB do you already have? (Postgres → start with pgvector)
4. Do you have an ops team? (no → managed)

## Pitfalls
- Changed the embedder, did not re-index → silent garbage
- Deleted docs stayed in the index → outdated/wrong info
- Metadata lives in JSON, so SQL cannot filter on it → make important filter fields separate columns
- Loading all vectors into Python on every query → RAM spike (OK here for small data)

## How this project uses it

| Concept | File / function |
|---|---|
| Schema (meta, documents, chunks, CASCADE) | `vstore_sqlite.py` → `SCHEMA` |
| float32 BLOB encoding | `to_blob()`, `from_blob()` |
| Embedder/dim consistency check | `SQLiteVectorStore._check_embedder()` |
| Content hashing + upsert in transaction | `content_hash()`, `upsert_document()` |
| Folder sync (add/update/skip/delete) | `ingest_folder()` → `IngestReport` |
| Brute-force search + SQL filter | `search(doc_id=...)` |
| CLI ingest/search/ask/stats | `main.py` |
