# Vector Store Persistence + Incremental Ingestion: concepts (Hinglish)

Project 01 ka vector store **RAM mein** tha: program band hua to sab gaya, aur har start pe saare docs
**dobara embed** hote the (paid API pe paisa + time). Production mein chahiye:

1. **Persistence**: index disk pe rahe, restart ke baad bhi
2. **Incremental ingestion**: sirf naye/badle docs embed ho, hataaye gaye docs index se bhi hatein
3. **Consistency**: galat embedder ke vectors mix na ho

## Flow

```
            ┌────────────── ingest_folder(data/) ──────────────┐
            │                                                  │
  har file ─┼─► sha256(content) ──► DB mein same hash?          │
            │                         │                        │
            │          haan ◄─────────┴────────► nahi          │
            │           │                         │            │
            │      "unchanged"             chunk + embed        │
            │      (0 API calls)           TRANSACTION:         │
            │                                delete old chunks  │
            │                                upsert document    │
            │                                insert new chunks  │
            │                              "added"/"updated"    │
            │                                                  │
  DB mein hai, folder mein nahi? ──► delete (chunks CASCADE) "deleted"
            └──────────────────────────────────────────────────┘

  search(query) ──► embed query ──► SELECT embeddings (WHERE filter) ──► cosine sab se ──► top-k
```

## 1. Vectors ko store kaise karein?

| Format | Size (512 dims) | Note |
|---|---|---|
| JSON text `[0.12, -0.4, ...]` | ~5-6 KB | Readable, slow parse |
| **float32 BLOB** (yahan) | 2 KB | `array("f").tobytes()`, compact aur fast |
| float16 / int8 quantized | 1 KB / 512 B | Real DBs mein, thoda accuracy loss |
| Binary quantization | 64 B | Bahut fast pre-filter, phir re-score |

## 2. Schema

```
 meta        (embedder="local", dim=512)          ◄── safety check
 documents   (doc_id, content_hash, chunk_count, updated_at)
 chunks      (id, doc_id → documents ON DELETE CASCADE, position, text, metadata JSON, embedding BLOB)
```
- `documents` table hi incremental sync ka "memory" hai: kaunsa file kis hash ke saath index hua
- `ON DELETE CASCADE`: document hataya to uske chunks apne aap hat jaate hain (orphan chunks nahi bachte)

## 3. Incremental ingestion: content hashing

```
 Day 1: 5 files ─► 5 added, 8 chunks embedded
 Day 2: same     ─► 5 unchanged, 0 embedded           ◄── yahi paisa bachata hai
 Day 3: shipping.md edit, refund_policy.md delete
                 ─► updated=[shipping.md], deleted=[refund_policy.md]
```
Details jo production mein matter karti hain:
- **Hash content, not mtime**: file "touch" hone se mtime badalta hai, content nahi
- **Doc-level vs chunk-level**: yahan doc badla to uske saare chunks re-embed. Better: har chunk ka hash rakho,
  sirf badle chunks re-embed (bade docs mein bada fayda)
- **Transaction**: delete-old + insert-new ek transaction mein (`with self.db:`), warna crash pe doc aadha index hota
- **Deletes bhoolna** sabse common bug hai: hataayi hui policy ab bhi retrieve hoti rehti hai aur bot purani info deta hai

## 4. Embedder consistency

Har embedding model ka apna "vector space" hota hai. Model A ke vectors ko model B ki query se compare
karna = garbage results, bina kisi error ke! Isliye `meta` table mein embedder name + dim save karte hain
aur mismatch pe **hard error** ("Re-index into a new DB"). Model upgrade = **poora re-index** (naye DB/collection
mein banao, phir switch karo = blue/green re-indexing).

## 5. Brute force vs ANN (Approximate Nearest Neighbour)

Yahan search = saare vectors load karo aur sab se cosine = **O(N)**.
```
 10k chunks    → ~ms,  bilkul theek
 1M chunks     → har query pe 1M cosine = slow + RAM heavy
 100M chunks   → impossible
```
Real vector DBs **ANN index** use karte hain: thoda accuracy chhod ke bahut speed.

**HNSW (Hierarchical Navigable Small World)**, sabse popular:
```
 Layer 2:  A ─────────────── F                 (bahut kam nodes, lambe jumps)
           │                 │
 Layer 1:  A ──── C ──── E ─ F ──── H          (zyada nodes)
           │      │      │   │      │
 Layer 0:  A─B─C─D─E─F─G─H─I─J ...             (saare nodes, chhote jumps)

 Search: upar se shuru, har layer pe query ke sabse paas wale neighbour pe jump karo,
         neeche utro, repeat. Highway se colony tak jaane jaisa. ~O(log N)
```
Doosre ANN types: **IVF** (vectors ko clusters mein baanto, sirf paas ke clusters search karo),
**PQ** (vectors compress karo), **ScaNN**, **DiskANN** (disk-based, huge data).
Trade-off knob: recall (sahi neighbours mile?) vs latency vs memory.

## 6. Real vector DBs: comparison

| DB | Type | Kab use karein | Note |
|---|---|---|---|
| **FAISS** | Library (in-process) | Research, batch jobs, custom infra | Meta ka; super fast; persistence/filtering khud handle |
| **Chroma** | Embedded / server | Prototypes, local apps | `pip install`, SQLite jaisa feel; simple API |
| **pgvector** | Postgres extension | Already Postgres hai; SQL joins + filters + transactions chahiye | HNSW/IVFFlat index; ek hi DB mein app data + vectors |
| **Qdrant** | Dedicated server (Rust) | Production, heavy metadata filtering | Payload filters strong, quantization, self-host ya cloud |
| **Pinecone** | Managed SaaS | Ops nahi karna, scale chahiye | Serverless, paid; vendor lock-in |
| **Weaviate / Milvus** | Dedicated server | Bada scale, hybrid search built-in | Milvus billions of vectors ke liye |
| **Elasticsearch / OpenSearch** | Search engine + vectors | BM25 + vector hybrid ek jagah | Already ES hai to achha |
| **SQLite + sqlite-vec** | Embedded extension | Edge/mobile/local apps | Yeh project ka "grown-up" version |

Choose karne ke sawaal:
1. Kitne vectors? (<100k: kuch bhi chalega, brute force bhi)
2. Filters kitne important hain? (multi-tenant → strong filtering)
3. Already kaunsa DB hai? (Postgres → pgvector se shuru karo)
4. Ops team hai? (nahi → managed)

## Pitfalls
- Embedder badla, re-index nahi kiya → silent garbage
- Deleted docs index mein reh gaye → purani/galat info
- Metadata JSON mein hai, SQL filter nahi ho sakta → important filter fields ko alag columns banao
- Har query pe saare vectors Python mein load → RAM spike (yahan chhote data ke liye OK)

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Schema (meta, documents, chunks, CASCADE) | `vstore_sqlite.py` → `SCHEMA` |
| float32 BLOB encoding | `to_blob()`, `from_blob()` |
| Embedder/dim consistency check | `SQLiteVectorStore._check_embedder()` |
| Content hashing + upsert in transaction | `content_hash()`, `upsert_document()` |
| Folder sync (add/update/skip/delete) | `ingest_folder()` → `IngestReport` |
| Brute-force search + SQL filter | `search(doc_id=...)` |
| CLI ingest/search/ask/stats | `main.py` |
